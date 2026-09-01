"""
Tests for core/webhook_listener.py.

Verifies:
1. HMAC SHA-256 webhook signature validation (valid, tampered, missing).
2. Traceback log parsing.
3. Idempotency enforcement on duplicate event deliveries.
4. End-to-end webhook event handling to PR creation or commit comment (mocked).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from unittest.mock import MagicMock, patch

from core import webhook_listener
from core.models import AnalysisResult, ErrorType, Issue


def test_signature_verification():
    print("\n--- Test: Webhook HMAC SHA-256 signature verification ---")
    secret = "my_super_secret_webhook_key"
    payload = b'{"action": "completed", "workflow_run": {"id": 12345}}'

    # Compute valid signature
    valid_hash = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    valid_header = f"sha256={valid_hash}"

    # 1. Valid signature
    assert webhook_listener.verify_signature(payload, valid_header, secret) is True
    print("  Valid signature accepted.")

    # 2. Tampered payload
    tampered_payload = b'{"action": "completed", "workflow_run": {"id": 99999}}'
    assert webhook_listener.verify_signature(tampered_payload, valid_header, secret) is False
    print("  Tampered payload rejected.")

    # 3. Invalid secret / signature
    assert webhook_listener.verify_signature(payload, "sha256=invalid_hash_value", secret) is False
    assert webhook_listener.verify_signature(payload, None, secret) is False
    assert webhook_listener.verify_signature(payload, valid_header, "") is False
    print("  Missing/invalid headers rejected.")

    print("  PASS")


def test_traceback_parsing():
    print("\n--- Test: Python traceback log parsing ---")
    sample_log = """
2026-09-01T10:00:00Z Running test suite...
Traceback (most recent call last):
  File "src/calculator.py", line 42, in calculate_total
    total = price + tax
NameError: name 'price' is not defined
Error: Process completed with exit code 1.
"""
    extracted = webhook_listener.parse_python_traceback(sample_log)
    assert extracted is not None
    assert extracted.file_path == "src/calculator.py"
    assert extracted.line_number == 42
    assert extracted.error_type == "NameError"
    assert "NameError: name 'price' is not defined" in extracted.error_message
    print(f"  Parsed: {extracted.file_path}:{extracted.line_number} -> {extracted.error_message}")

    print("  PASS")


def test_idempotency():
    print("\n--- Test: Idempotency protection against duplicate deliveries ---")
    test_run_id = 987654321
    
    assert webhook_listener.is_run_processed(test_run_id) is False
    webhook_listener.mark_run_processed(test_run_id)
    assert webhook_listener.is_run_processed(test_run_id) is True

    # Test handling with already processed run_id
    payload = {
        "action": "completed",
        "workflow_run": {
            "id": test_run_id,
            "conclusion": "failure",
        }
    }
    res = webhook_listener.handle_workflow_run_event(payload, github_token="ghp_test")
    assert res["status"] == "skipped"
    assert "already processed" in res["reason"]
    print("  Duplicate webhook event skipped cleanly.")

    print("  PASS")


def test_end_to_end_webhook_flow_mocked():
    print("\n--- Test: End-to-end webhook failure -> fix -> PR flow (mocked) ---")
    run_id = 1122334455
    payload = {
        "action": "completed",
        "workflow_run": {
            "id": run_id,
            "conclusion": "failure",
            "head_sha": "abcdef1234567890",
            "head_branch": "main",
            "error_log": 'File "src/math_ops.py", line 10\n    return math.pi * r ** 2\nNameError: name \'math\' is not defined',
        },
        "repository": {
            "name": "sample-repo",
            "owner": {"login": "testuser"},
        },
    }

    mock_file_content = "def area(r):\n    return math.pi * r ** 2\n"

    # Mock fetch_file_content, create_pull_request
    mock_pr_res = MagicMock(
        success=True,
        pr_url="https://github.com/testuser/sample-repo/pull/42",
        pr_number=42,
        branch_name="fixmate/auto-fix-ci-1122334455",
    )

    with patch("core.webhook_listener.fetch_file_content", return_value=mock_file_content):
        with patch("core.github_integration.create_pull_request", return_value=mock_pr_res):
            res = webhook_listener.handle_workflow_run_event(payload, github_token="ghp_test_token")
            assert res["status"] == "pr_opened"
            assert res["pr_number"] == 42
            assert "pull/42" in res["pr_url"]
            print(f"  Successfully triggered pipeline and opened PR #{res['pr_number']}.")

    print("  PASS")


def main() -> int:
    try:
        test_signature_verification()
        test_traceback_parsing()
        test_idempotency()
        test_end_to_end_webhook_flow_mocked()
        print("\n" + "=" * 60)
        print("ALL WEBHOOK LISTENER TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! WEBHOOK LISTENER TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
