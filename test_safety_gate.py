"""
Tests for core/safety_gate.py.

Verifies:
1. Low-risk rating for clean localized repairs.
2. High-risk rating and PR blocking when Bandit catches dangerous constructs (e.g. eval).
3. Signature change detection for breaking API changes.
4. Clean degradation when Bandit is unavailable.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from core import safety_gate


def test_clean_fix_assessment():
    print("\n--- Test: Clean localized fix assessment ---")
    orig = "def add(a, b):\n    return a + b\n"
    fixed = "def add(a, b):\n    return a + b\n"

    risk = safety_gate.assess_risk(orig, fixed)
    assert risk.level == "low"
    assert risk.blocks_pr is False
    assert risk.signature_changed is False
    assert len(risk.new_bandit_findings) == 0
    print(f"  Clean fix assessed as {risk.level} risk.")
    print("  PASS")


def test_signature_change_detection():
    print("\n--- Test: Breaking signature alteration detection ---")
    orig = "def fetch_user(user_id):\n    return user_id\n"
    fixed = "def fetch_user(user_id, api_token, force=True):\n    return user_id\n"

    sig_changed, reasons = safety_gate.check_signature_changes(orig, fixed)
    assert sig_changed is True
    assert len(reasons) == 1
    assert "fetch_user" in reasons[0]

    risk = safety_gate.assess_risk(orig, fixed)
    assert risk.signature_changed is True
    assert any("modified" in r for r in risk.reasons)
    print(f"  Signature alteration detected: {risk.reasons}")
    print("  PASS")


def test_real_bandit_vulnerability_detection():
    print("\n--- Test: Real Bandit vulnerability detection ---")
    orig = "def compute(expr):\n    return 0\n"
    # Fix replaces safe code with dangerous eval()
    fixed = "def compute(expr):\n    return eval(expr)\n"

    risk = safety_gate.assess_risk(orig, fixed)
    print(f"  Bandit ran: {risk.bandit_executed}")
    print(f"  Risk level: {risk.level}")
    print(f"  Blocks PR: {risk.blocks_pr}")
    print(f"  New findings count: {len(risk.new_bandit_findings)}")

    if risk.bandit_executed:
        assert risk.level == "high"
        assert risk.blocks_pr is True
        assert any(f.test_id == "B307" or "eval" in f.text.lower() for f in risk.new_bandit_findings)
        print("  Real Bandit scan correctly detected eval() vulnerability (B307) and blocked PR.")
    else:
        print("  Bandit not installed in environment; skipping live assertion.")

    print("  PASS")


def test_bandit_degradation_when_unavailable():
    print("\n--- Test: Graceful degradation when Bandit unavailable ---")
    with patch("core.safety_gate.is_bandit_available", return_value=False):
        orig = "def f(x): return x"
        fixed = "def f(x): return x + 1"
        risk = safety_gate.assess_risk(orig, fixed)
        assert risk.bandit_executed is False
        assert any("not installed" in r for r in risk.reasons)
        print("  Handled missing Bandit scanner cleanly.")

    print("  PASS")


def main() -> int:
    try:
        test_clean_fix_assessment()
        test_signature_change_detection()
        test_real_bandit_vulnerability_detection()
        test_bandit_degradation_when_unavailable()
        print("\n" + "=" * 60)
        print("ALL SAFETY GATE TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! SAFETY GATE TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
