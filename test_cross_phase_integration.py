"""
Cross-Phase Integration Audit Test Suite for FixMate AI.

Verifies:
1. Safety Gate PR blocking in both UI logic and Webhook bot logic.
2. Analytics Store schema consistency between UI and Webhook events.
3. Calibration impact on issue confidence before and after >=10 samples.
4. Multi-file context gathering delivery to LLM escalation prompt.
5. End-to-end JavaScript vs Python language dispatching.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core import analytics_store, calibration, context_gatherer, engine, llm_client, models, safety_gate, webhook_listener


def test_safety_gate_pr_blocking_sites():
    print("\n--- Cross-Phase 1: Safety Gate PR Block Call Sites ---")
    # 1. Dangerous code that introduces eval()
    orig = "def compute(x): return x * 2"
    fixed_dangerous = "def compute(x): return eval(x)"

    assessment = safety_gate.assess_risk(orig, fixed_dangerous)
    assert assessment.blocks_pr is True
    print(f"  Safety assessment correctly blocks dangerous fix: {assessment.summary}")

    # 2. Webhook listener check
    with patch("core.webhook_listener.is_run_processed", return_value=False), \
         patch("core.webhook_listener.mark_run_processed"), \
         patch("core.webhook_listener.run_pipeline") as mock_run, \
         patch("core.webhook_listener.post_commit_comment") as mock_comment, \
         patch("core.webhook_listener.fetch_file_content", return_value="def compute(x): return x"):

        mock_res = models.AnalysisResult(
            original_code=orig,
            fixed_code=fixed_dangerous,
            issues=[],
            explanation="Unsafe fix",
            verified=True,
            attempts=1,
            safety_assessment=assessment,
        )
        mock_run.return_value = mock_res

        payload = {
            "workflow_run": {
                "id": 8888999,
                "conclusion": "failure",
                "head_sha": "abc1234",
                "head_branch": "main",
            },
            "repository": {
                "owner": {"login": "testorg"},
                "name": "testrepo",
            },
        }

        res = webhook_listener.handle_workflow_run_event(payload, github_token="fake_token")
        assert res["status"] == "safety_gate_blocked"
        assert mock_comment.called
        print("  Webhook listener correctly blocked PR and posted safety comment.")
    print("  PASS")


def test_analytics_store_schema_consistency():
    print("\n--- Cross-Phase 2: Analytics Store Schema Consistency (UI vs Webhook) ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_consistency.db"

        # 1. Event from Streamlit UI
        ui_res = models.AnalysisResult(
            original_code="import math",
            fixed_code="import math\nprint(math.pi)",
            issues=[models.Issue(models.ErrorType.MISSING_IMPORT, 1, "missing", confidence=0.95)],
            explanation="Added print",
            verified=True,
            attempts=1,
            source="local_engine",
        )
        analytics_store.record_result(ui_res, repo_name="", file_path="interactive_editor", db_path=db_path)

        # 2. Event from Webhook CI trigger
        ci_res = models.AnalysisResult(
            original_code="def calc():",
            fixed_code="def calc(): pass",
            issues=[models.Issue(models.ErrorType.SYNTAX_ERROR, 1, "missing colon", confidence=0.85)],
            explanation="Fixed syntax",
            verified=True,
            attempts=2,
            source="groq_llm",
        )
        analytics_store.record_result(ci_res, repo_name="myorg/backend", file_path="src/calc.py", db_path=db_path)

        # Query history
        history = analytics_store.get_recent_history(limit=10, db_path=db_path)
        assert len(history) == 2

        expected_keys = {"id", "timestamp", "repo_name", "file_path", "error_types", "issue_count", "verified", "source", "attempts", "was_accepted"}
        for record in history:
            assert set(record.keys()) == expected_keys
            assert isinstance(record["id"], int)
            assert isinstance(record["verified"], bool)
            assert isinstance(record["was_accepted"], bool)

        print("  Both UI and Webhook events stored with identical schema and typed fields.")
    print("  PASS")


def test_calibration_confidence_shift():
    print("\n--- Cross-Phase 3: Calibration Confidence Shift On Real History ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cal_shift.db"

        # Before history: static score
        score_before, reason_before = calibration.calibrated_confidence("syntax_error", 0.70, db_path=db_path)
        assert score_before == 0.70
        assert "insufficient history" in reason_before

        # Seed 15 successful accepted fixes
        for _ in range(15):
            res = models.AnalysisResult(
                original_code="def f():",
                fixed_code="def f(): pass",
                issues=[models.Issue(models.ErrorType.SYNTAX_ERROR, 1, "syntax", confidence=0.70)],
                explanation="fixed",
                verified=True,
                attempts=1,
            )
            analytics_store.record_result(res, was_accepted=True, db_path=db_path)

        # After history: calibrated score
        score_after, reason_after = calibration.calibrated_confidence("syntax_error", 0.70, db_path=db_path)
        assert score_after > score_before
        assert "calibrated from 15 recent runs" in reason_after
        print(f"  Confidence calibrated from {score_before} -> {score_after} ({reason_after})")
    print("  PASS")


def test_multifile_context_reaching_llm_call():
    print("\n--- Cross-Phase 4: Multi-File Context Flow into LLM Escalation ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)
        src_dir = repo_dir / "pkg"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text("", encoding="utf-8")
        (src_dir / "helper.py").write_text("def helper_fn(): return 42\n", encoding="utf-8")
        main_file = src_dir / "main.py"
        broken_code = "from pkg.helper import helper_fn\ndef run(): return helper_fn() + extra_undef\n"
        main_file.write_text(broken_code, encoding="utf-8")

        with patch("core.llm_client.is_available", return_value=True), \
             patch("core.llm_client.analyze_and_fix") as mock_llm:

            mock_llm.return_value = llm_client.LlmResponse(
                fixed_code="from pkg.helper import helper_fn\ndef run(): return helper_fn()\n",
                explanation="Removed undefined extra_undef",
                error_type="undefined_variable",
                raw_latency_s=0.25,
            )

            res = engine.run_pipeline(
                code=broken_code,
                use_cloud_llm=True,
                file_path=str(main_file),
                repo_root=str(repo_dir),
            )

            assert mock_llm.called
            call_kwargs = mock_llm.call_args[1]
            extra_ctx = call_kwargs.get("extra_context", "")
            assert "pkg/helper.py" in extra_ctx or "helper.py" in extra_ctx
            assert "helper_fn" in extra_ctx
            print(f"  Multi-file context successfully bundled into LLM call:\n  {extra_ctx[:100]}...")
    print("  PASS")


def test_language_dispatch_end_to_end():
    print("\n--- Cross-Phase 5: Language Dispatching (Python vs JavaScript) ---")
    # 1. Python Snippet
    py_code = "def add(a, b):\n    return a + b\n"
    py_res = engine.run_local_pipeline(py_code, file_path="math.py")
    assert py_res.source == "local_engine"

    # 2. JavaScript Snippet
    js_code = "function add(a, b) { return a + b; }"
    js_res = engine.run_local_pipeline(js_code, file_path="math.js")
    assert js_res.source == "local_engine_js"
    print("  run_local_pipeline dispatched correctly to local_engine (Python) and local_engine_js (JS).")
    print("  PASS")


def main() -> int:
    try:
        test_safety_gate_pr_blocking_sites()
        test_analytics_store_schema_consistency()
        test_calibration_confidence_shift()
        test_multifile_context_reaching_llm_call()
        test_language_dispatch_end_to_end()
        print("\n" + "=" * 60)
        print("ALL CROSS-PHASE INTEGRATION CHECKS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"\n!! CROSS-PHASE INTEGRATION CHECK FAILED: {exc}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
