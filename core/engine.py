"""
The FixMate pipeline.

This is deliberately built like a small multi-agent system even though it
runs entirely offline: a dedicated detector "owns" each error class end to
end (detect -> fix), the engine loops detect -> fix -> re-verify until the
code parses clean or it runs out of attempts, and every step is logged to
a `trace` so the UI can show its work like a live agent log.

If a Groq API key is configured and the caller opts in, the engine can also
hand off to the cloud LLM — either as the primary analyzer, or as a
fallback when the local detectors come up empty (i.e. the bug is outside
the three classes the offline engine understands).
"""

from __future__ import annotations

import ast

from core import config
from core.detectors import MissingImportDetector, SyntaxErrorDetector, UndefinedVariableDetector
from core.models import AnalysisResult, ErrorType, Issue, PipelineStep
from core import llm_client
from core import sandbox
from core import test_generator


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _summarize(issues: list[Issue]) -> str:
    if not issues:
        return "No issues found by the local engine."
    by_type: dict[ErrorType, list[Issue]] = {}
    for issue in issues:
        by_type.setdefault(issue.error_type, []).append(issue)

    parts = []
    for etype, group in by_type.items():
        lines = sorted({i.line for i in group if i.line is not None})
        where = f"line {lines[0]}" if len(lines) == 1 else f"lines {', '.join(map(str, lines))}"
        label = {
            ErrorType.MISSING_IMPORT: "missing import(s)",
            ErrorType.SYNTAX_ERROR: "a syntax error",
            ErrorType.UNDEFINED_VARIABLE: "undefined variable(s)",
        }.get(etype, str(etype.value))
        parts.append(f"{label} ({where})")
    return "Found " + ", ".join(parts) + "."


def run_local_pipeline(code: str, max_attempts: int | None = None) -> AnalysisResult:
    """Offline, deterministic pipeline. No network calls, no API key needed."""
    max_attempts = max_attempts or config.settings.max_fix_attempts
    trace: list[PipelineStep] = [
        PipelineStep("Detect", "info", "Scanning with 3 local detectors: syntax, imports, undefined names."),
    ]

    current = code
    all_issues: list[Issue] = []
    attempt = 0

    for attempt in range(1, max_attempts + 1):
        syntax_issues = SyntaxErrorDetector().detect(current)
        if syntax_issues:
            all_issues.extend(syntax_issues)
            trace.append(PipelineStep(
                f"Attempt {attempt} · Syntax scan", "warn",
                f"Line {syntax_issues[0].line}: {syntax_issues[0].message}",
            ))
            fixed = SyntaxErrorDetector().fix(current, syntax_issues)
            current = fixed.fixed_code
            trace.append(PipelineStep(
                f"Attempt {attempt} · Repair syntax",
                "ok" if _parses(current) else "warn",
                fixed.explanation,
            ))
            continue  # code changed shape — re-run the whole scan from the top

        mi_issues = MissingImportDetector().detect(current)
        uv_issues = UndefinedVariableDetector().detect(current)

        if not mi_issues and not uv_issues:
            trace.append(PipelineStep("Verify", "ok", "Code parses cleanly and no known issue patterns remain."))
            break

        if mi_issues:
            all_issues.extend(mi_issues)
            fixed = MissingImportDetector().fix(current, mi_issues)
            current = fixed.fixed_code
            trace.append(PipelineStep(f"Attempt {attempt} · Add missing imports", "ok", fixed.explanation))

        if uv_issues:
            all_issues.extend(uv_issues)
            fixed = UndefinedVariableDetector().fix(current, uv_issues)
            current = fixed.fixed_code
            trace.append(PipelineStep(f"Attempt {attempt} · Rename undefined names", "ok", fixed.explanation))
    else:
        trace.append(PipelineStep("Verify", "warn", f"Stopped after {max_attempts} attempts."))

    verified = _parses(current)
    trace.append(PipelineStep(
        "Final check", "ok" if verified else "fail",
        "ast.parse() succeeds on the fixed code." if verified else "The fixed code still fails to parse.",
    ))

    return AnalysisResult(
        original_code=code,
        fixed_code=current,
        issues=all_issues,
        explanation=_summarize(all_issues),
        verified=verified,
        attempts=attempt,
        trace=trace,
        source="local_engine",
    )


def run_pipeline(
    code: str,
    use_cloud_llm: bool = False,
    error_message: str = "",
    verify_in_sandbox: bool = False,
    generate_tests: bool = False,
) -> AnalysisResult:
    """Public entry point. Runs the local engine first; optionally escalates
    to the Groq cloud LLM either by user choice, or automatically when the
    local engine finds nothing (the bug may be outside its 3 known classes).

    Optionally runs sandboxed container verification and automated test generation.
    """
    result = run_local_pipeline(code)

    should_escalate = use_cloud_llm and (not result.issues or not result.verified)
    if use_cloud_llm:
        if not llm_client.is_available():
            result.trace.append(PipelineStep(
                "Cloud LLM", "warn",
                "Cloud analysis requested but no Groq API key is configured — showing local engine result.",
            ))
        elif not should_escalate:
            result.trace.append(PipelineStep(
                "Cloud LLM", "info", "Skipped — local engine already found and verified a fix.",
            ))
        else:
            result.trace.append(PipelineStep("Cloud LLM", "info", f"Escalating to Groq ({config.settings.groq_model})..."))
            try:
                llm_result = llm_client.analyze_and_fix(code, error_message)
                verified = _parses(llm_result.fixed_code)
                result.trace.append(PipelineStep(
                    "Cloud LLM", "ok" if verified else "warn",
                    f"Groq responded in {llm_result.raw_latency_s:.2f}s.",
                ))
                result = AnalysisResult(
                    original_code=code,
                    fixed_code=llm_result.fixed_code,
                    issues=result.issues or [Issue(
                        error_type=ErrorType.UNKNOWN, line=None,
                        message="Detected by cloud LLM (outside local engine's 3 known classes).",
                    )],
                    explanation=llm_result.explanation,
                    verified=verified,
                    attempts=result.attempts,
                    trace=result.trace,
                    source="groq_llm",
                )
            except llm_client.LlmUnavailable as exc:
                result.trace.append(PipelineStep("Cloud LLM", "fail", str(exc)))

    # Optional stage: Sandboxed verification in Docker
    if verify_in_sandbox:
        if not sandbox.is_available():
            _, reason = sandbox.get_availability_status()
            result.trace.append(PipelineStep("Sandbox Verify", "warn", f"Docker unavailable: {reason}"))
            result.sandbox_result = sandbox.VerificationResult(
                before_ok=False,
                after_ok=False,
                before_output="",
                after_output="",
                error=reason,
                runs_executed=False,
            )
        else:
            v_res = sandbox.verify_fix_in_sandbox(result.original_code, result.fixed_code)
            result.sandbox_result = v_res
            if v_res.after_ok:
                detail = f"Before: {'ran cleanly' if v_res.before_ok else 'crashed'} · After: ran cleanly"
                result.trace.append(PipelineStep("Sandbox Verify", "ok", detail))
            else:
                detail = f"After: failed inside container ({v_res.after_output[:60]}...)" if len(v_res.after_output) > 60 else f"After: failed ({v_res.after_output})"
                result.trace.append(PipelineStep("Sandbox Verify", "fail", detail))

    # Optional stage: Automated Test Generation
    if generate_tests:
        if not test_generator.is_available():
            result.trace.append(PipelineStep(
                "Test Generator", "info",
                "Test generation requested but no Groq API key configured — skipped.",
            ))
        else:
            suite = test_generator.generate_tests(result.fixed_code)
            if suite.cases:
                result.trace.append(PipelineStep(
                    "Test Generator", "ok",
                    f"Generated {len(suite.cases)} test case(s) ({suite.latency_s:.2f}s).",
                ))
                if sandbox.is_available():
                    suite = test_generator.execute_test_suite(result.fixed_code, suite)
                    if suite.all_passed:
                        result.trace.append(PipelineStep(
                            "Test Execution", "ok",
                            f"All {len(suite.cases)} generated test case(s) passed in sandbox.",
                        ))
                    else:
                        failed_count = sum(1 for c in suite.cases if not c.passed)
                        result.trace.append(PipelineStep(
                            "Test Execution", "warn",
                            f"{failed_count}/{len(suite.cases)} test case(s) failed in sandbox.",
                        ))
                else:
                    result.trace.append(PipelineStep(
                        "Test Execution", "info",
                        "Execution skipped — Docker sandbox unavailable.",
                    ))
            elif suite.error:
                result.trace.append(PipelineStep("Test Generator", "fail", suite.error))

            result.test_suite = suite

    return result
