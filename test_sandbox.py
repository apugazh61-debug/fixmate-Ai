"""
Tests for core/sandbox.py.

Verifies:
1. Live Docker availability detection (returns bool and reason, never crashes).
2. Graceful degradation when Docker is unavailable.
3. Correct capture of exit code, stdout, stderr, timeout, and VerificationResult.
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

from core import sandbox


def test_availability_detection():
    print("\n--- Test: Docker availability detection ---")
    available = sandbox.is_available()
    status, reason = sandbox.get_availability_status()
    print(f"  is_available: {available}")
    print(f"  status: {status}")
    print(f"  reason: {reason}")
    assert isinstance(available, bool)
    assert isinstance(reason, str)
    assert available == status
    print("  PASS")


def test_graceful_degradation_when_unavailable():
    print("\n--- Test: Graceful degradation when Docker unavailable ---")
    with patch("core.sandbox.get_availability_status", return_value=(False, "Docker daemon not running.")):
        assert sandbox.is_available() is False

        # run_in_sandbox must not crash
        res = sandbox.run_in_sandbox("print('hello')")
        assert res.success is False
        assert res.exit_code == -1
        assert "Docker daemon not running" in res.error
        print("  run_in_sandbox handled unavailable state cleanly.")

        # verify_fix_in_sandbox must not crash
        v_res = sandbox.verify_fix_in_sandbox("x = 1", "x = 2")
        assert v_res.runs_executed is False
        assert "Docker daemon not running" in v_res.error
        print("  verify_fix_in_sandbox handled unavailable state cleanly.")

    print("  PASS")


def test_sandbox_execution_mocked():
    print("\n--- Test: Sandbox execution output parsing (mocked) ---")
    with patch("core.sandbox.get_availability_status", return_value=(True, "Docker reachable.")):
        # 1. Success case
        mock_proc_ok = MagicMock()
        mock_proc_ok.returncode = 0
        mock_proc_ok.stdout = "42\n"
        mock_proc_ok.stderr = ""
        with patch("subprocess.run", return_value=mock_proc_ok):
            res = sandbox.run_in_sandbox("print(42)")
            assert res.success is True
            assert res.exit_code == 0
            assert res.stdout == "42\n"
            assert res.combined_output == "42"

        # 2. Failure / Exception in user code
        mock_proc_err = MagicMock()
        mock_proc_err.returncode = 1
        mock_proc_err.stdout = ""
        mock_proc_err.stderr = "NameError: name 'item' is not defined\n"
        with patch("subprocess.run", return_value=mock_proc_err):
            res = sandbox.run_in_sandbox("print(item)")
            assert res.success is False
            assert res.exit_code == 1
            assert "NameError" in res.combined_output

        # 3. Timeout case
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=5)):
            res = sandbox.run_in_sandbox("while True: pass")
            assert res.success is False
            assert res.timed_out is True
            assert "timed out" in res.stderr

        # 4. verify_fix_in_sandbox paired run
        with patch("subprocess.run", side_effect=[mock_proc_err, mock_proc_ok]):
            v_res = sandbox.verify_fix_in_sandbox("print(item)", "print(42)")
            assert v_res.runs_executed is True
            assert v_res.before_ok is False
            assert v_res.after_ok is True
            assert "NameError" in v_res.before_output
            assert v_res.after_output == "42"

    print("  PASS")


def main() -> int:
    try:
        test_availability_detection()
        test_graceful_degradation_when_unavailable()
        test_sandbox_execution_mocked()
        print("\n" + "=" * 60)
        print("ALL SANDBOX TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! SANDBOX TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
