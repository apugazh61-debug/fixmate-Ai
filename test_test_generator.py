"""
Tests for core/test_generator.py.

Verifies:
1. LLM availability detection (reusing config settings).
2. Graceful degradation when no API key or package is present.
3. Test case JSON parsing and structure from LLM output (mocked).
4. Sandbox execution of test cases and reporting of pass/fail (mocked).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

from core import config
from core import test_generator
from core.sandbox import SandboxRunResult


def test_availability_and_missing_key():
    print("\n--- Test: LLM missing key handling ---")
    os.environ.pop("GROQ_API_KEY", None)
    config.settings = config.load_settings()

    assert test_generator.is_available() is False
    res = test_generator.generate_tests("def add(a, b): return a + b")
    assert res.test_code == ""
    assert "No GROQ_API_KEY" in res.error
    assert len(res.cases) == 0
    print("  generate_tests handled missing key gracefully.")
    print("  PASS")


def test_mocked_llm_generation():
    print("\n--- Test: Test generation from Groq LLM (mocked) ---")
    mock_payload = {
        "test_code": "def test_add_positive():\n    assert add(1, 2) == 3\n\ndef test_add_zero():\n    assert add(0, 0) == 0",
        "tests": [
            {
                "name": "test_add_positive",
                "description": "Tests normal addition",
                "code": "def test_add_positive():\n    assert add(1, 2) == 3"
            },
            {
                "name": "test_add_zero",
                "description": "Tests zero values",
                "code": "def test_add_zero():\n    assert add(0, 0) == 0"
            }
        ]
    }

    mock_choice = MagicMock()
    mock_choice.message.content = f"```json\n{import_json_dumps(mock_payload)}\n```"
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    config.settings = config.Settings(
        groq_api_key="gsk_mock_key",
        groq_model="llama-3.3-70b-versatile",
        max_fix_attempts=3,
    )

    with patch("core.test_generator._GROQ_AVAILABLE", True):
        with patch("core.test_generator.Groq", return_value=mock_client):
            suite = test_generator.generate_tests("def add(a, b): return a + b")
            assert suite.error == ""
            assert len(suite.cases) == 2
            assert suite.cases[0].name == "test_add_positive"
            assert suite.cases[1].name == "test_add_zero"
            print("  Test suite successfully parsed 2 test cases.")

    print("  PASS")


def test_mocked_sandbox_execution():
    print("\n--- Test: Test suite execution in sandbox (mocked) ---")
    suite = test_generator.TestSuiteResult(
        test_code="def test_add(): assert add(1, 2) == 3",
        cases=[
            test_generator.TestCaseResult(
                name="test_add",
                description="Tests add",
                code="def test_add(): assert add(1, 2) == 3",
            ),
            test_generator.TestCaseResult(
                name="test_fail",
                description="Tests fail",
                code="def test_fail(): assert False",
            ),
        ]
    )

    # 1. When sandbox is unavailable
    with patch("core.sandbox.is_available", return_value=False):
        suite_unavail = test_generator.execute_test_suite("def add(a, b): return a + b", suite)
        assert suite_unavail.executed is False
        assert "Cannot execute tests in sandbox" in suite_unavail.error
        print("  execute_test_suite handled unavailable sandbox cleanly.")

    # 2. When sandbox is available: 1 passes, 1 fails
    with patch("core.sandbox.is_available", return_value=True):
        pass_run = SandboxRunResult(success=True, exit_code=0, stdout="__FIXMATE_TEST_PASS__\n", stderr="")
        fail_run = SandboxRunResult(success=False, exit_code=1, stdout="", stderr="AssertionError")

        with patch("core.sandbox.run_in_sandbox", side_effect=[pass_run, fail_run]):
            suite_run = test_generator.execute_test_suite("def add(a, b): return a + b", suite)
            assert suite_run.executed is True
            assert suite_run.cases[0].passed is True
            assert suite_run.cases[1].passed is False
            assert suite_run.all_passed is False
            print("  execute_test_suite correctly identified pass/fail per test.")

    print("  PASS")


def import_json_dumps(d):
    import json
    return json.dumps(d)


def main() -> int:
    try:
        test_availability_and_missing_key()
        test_mocked_llm_generation()
        test_mocked_sandbox_execution()
        print("\n" + "=" * 60)
        print("ALL TEST GENERATOR TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! TEST GENERATOR TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
