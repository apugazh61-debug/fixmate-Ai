"""
Automatic test case generation and execution.

Uses Groq LLM (reusing the configuration in `core.config` and client pattern
from `core.llm_client`) to generate 2-3 pytest-style test cases covering
normal and edge cases for the fixed code.

Tests can then be executed inside `core.sandbox` to report pass/fail.
If no LLM or Docker is available, degrades cleanly without exceptions.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from core import config
from core import llm_client
from core import sandbox

try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False


TEST_GEN_SYSTEM_PROMPT = """You are FixMate's automated test generator.
Given a fixed Python code snippet, generate 2-3 concise test cases (using plain assert statements)
that verify the fixed code:
1. One or two normal/happy path test cases.
2. One edge-case test case (e.g. empty inputs, zero, special values).

Respond ONLY with strict JSON, no markdown fences, matching this shape:
{
  "test_code": "def test_case_1():\\n    assert ...\\n\\ndef test_case_2():\\n    assert ...",
  "tests": [
    {
      "name": "test_case_1",
      "description": "Tests normal execution",
      "code": "def test_case_1():\\n    assert ..."
    },
    {
      "name": "test_case_2",
      "description": "Tests edge case",
      "code": "def test_case_2():\\n    assert ..."
    }
  ]
}
"""


@dataclass
class TestCaseResult:
    """Result of a single generated test case."""
    name: str
    description: str
    code: str
    passed: bool = False
    output: str = ""
    error: str = ""


@dataclass
class TestSuiteResult:
    """Collection of generated test cases and execution summary."""
    test_code: str
    cases: list[TestCaseResult] = field(default_factory=list)
    all_passed: bool = False
    executed: bool = False
    error: str = ""
    latency_s: float = 0.0


def is_available() -> bool:
    """True if Groq LLM is installed and API key is set."""
    return llm_client.is_available()


def generate_tests(fixed_code: str, retries: int = 2) -> TestSuiteResult:
    """Generate 2-3 test cases using Groq LLM for the fixed code snippet."""
    if not _GROQ_AVAILABLE:
        return TestSuiteResult(
            test_code="",
            error="The `groq` package is not installed.",
        )
    if not config.settings.has_llm:
        return TestSuiteResult(
            test_code="",
            error="No GROQ_API_KEY configured — cannot generate test cases.",
        )

    client = Groq(api_key=config.settings.groq_api_key)
    user_prompt = f"FIXED PYTHON CODE:\n{fixed_code}"

    last_err: Exception | None = None
    for _ in range(retries):
        start = time.time()
        try:
            completion = client.chat.completions.create(
                model=config.settings.groq_model,
                messages=[
                    {"role": "system", "content": TEST_GEN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=1024,
            )
            latency = time.time() - start
            raw_content = completion.choices[0].message.content.strip()
            clean_json = (
                raw_content.removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            data = json.loads(clean_json)

            test_code = data.get("test_code", "")
            raw_tests = data.get("tests", [])

            cases: list[TestCaseResult] = []
            for item in raw_tests:
                cases.append(TestCaseResult(
                    name=item.get("name", "test_case"),
                    description=item.get("description", ""),
                    code=item.get("code", ""),
                ))

            return TestSuiteResult(
                test_code=test_code,
                cases=cases,
                latency_s=latency,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue

    return TestSuiteResult(
        test_code="",
        error=f"Test generation failed: {last_err}",
    )


def execute_test_suite(
    fixed_code: str,
    suite: TestSuiteResult,
    timeout: int = 5,
) -> TestSuiteResult:
    """Execute each generated test case against the fixed code in Docker sandbox."""
    if not suite.cases:
        return suite

    if not sandbox.is_available():
        _, reason = sandbox.get_availability_status()
        suite.executed = False
        suite.error = f"Cannot execute tests in sandbox: {reason}"
        return suite

    all_ok = True
    for case in suite.cases:
        # Build runnable harness for this single test
        harness = (
            f"{fixed_code}\n\n"
            f"{case.code}\n\n"
            f"if __name__ == '__main__':\n"
            f"    {case.name}()\n"
            f"    print('__FIXMATE_TEST_PASS__')\n"
        )
        res = sandbox.run_in_sandbox(harness, timeout=timeout)
        if res.success and "__FIXMATE_TEST_PASS__" in res.stdout:
            case.passed = True
            case.output = res.stdout.replace("__FIXMATE_TEST_PASS__", "").strip() or "Passed"
        else:
            case.passed = False
            case.output = res.combined_output
            case.error = res.stderr or res.error or "Assertion failed or test crashed."
            all_ok = False

    suite.executed = True
    suite.all_passed = all_ok and len(suite.cases) > 0
    return suite


def generate_and_run_tests(fixed_code: str, timeout: int = 5) -> TestSuiteResult:
    """Convenience pipeline: generate test cases and run them in sandbox."""
    suite = generate_tests(fixed_code)
    if suite.error or not suite.cases:
        return suite
    return execute_test_suite(fixed_code, suite, timeout=timeout)
