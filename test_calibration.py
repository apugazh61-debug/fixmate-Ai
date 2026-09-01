"""
Tests for core/calibration.py.

Verifies:
1. Handling of zero and low history without throwing.
2. Calibration adjustments based on empirical acceptance rates when samples >= 10.
3. Upward and downward confidence calibration movement.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from core import analytics_store
from core import calibration
from core.models import AnalysisResult, ErrorType, Issue


def test_zero_and_low_history():
    print("\n--- Test: Zero and low history handling ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cal_empty.db"

        # Zero samples
        score, reason = calibration.calibrated_confidence("syntax_error", 0.95, db_path=db_path)
        assert score == 0.95
        assert "insufficient history: 0/10" in reason
        print("  Handled 0 samples cleanly.")

        # Seed 4 samples (< 10 threshold)
        for _ in range(4):
            res = AnalysisResult(
                original_code="math.pi",
                fixed_code="import math\nmath.pi",
                issues=[Issue(error_type=ErrorType.MISSING_IMPORT, line=1, message="missing import", confidence=0.95)],
                explanation="Added math import",
                verified=True,
                attempts=1,
            )
            analytics_store.record_result(res, was_accepted=True, db_path=db_path)

        score_low, reason_low = calibration.calibrated_confidence("missing_import", 0.95, db_path=db_path)
        assert score_low == 0.95
        assert "insufficient history: 4/10" in reason_low
        print("  Handled 4 samples (< 10) cleanly.")

    print("  PASS")


def test_calibrated_confidence_movement():
    print("\n--- Test: Empirical confidence calibration with >= 10 samples ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cal_active.db"

        # 1. High acceptance (12/12 accepted = 100% acceptance rate)
        for _ in range(12):
            res = AnalysisResult(
                original_code="def f():",
                fixed_code="def f(): pass",
                issues=[Issue(error_type=ErrorType.SYNTAX_ERROR, line=1, message="syntax", confidence=0.80)],
                explanation="Fixed colon",
                verified=True,
                attempts=1,
            )
            analytics_store.record_result(res, was_accepted=True, db_path=db_path)

        score_high, reason_high = calibration.calibrated_confidence("syntax_error", 0.80, db_path=db_path)
        # Prior 0.80 + 1.0 acceptance -> blended (0.4 + 0.5 = 0.90)
        assert score_high > 0.80
        assert "calibrated from 12 recent runs (acceptance rate: 100%)" in reason_high
        print(f"  High acceptance calibrated score upward: 0.80 -> {score_high}")

        # 2. Low acceptance (12 samples: 3 accepted, 9 rejected = 25% acceptance rate)
        for i in range(12):
            res = AnalysisResult(
                original_code="print(it)",
                fixed_code="print(items)",
                issues=[Issue(error_type=ErrorType.UNDEFINED_VARIABLE, line=1, message="undefined", confidence=0.90)],
                explanation="Renamed variable",
                verified=True,
                attempts=1,
            )
            analytics_store.record_result(res, was_accepted=(i < 3), db_path=db_path)

        score_low, reason_low = calibration.calibrated_confidence("undefined_variable", 0.90, db_path=db_path)
        # Prior 0.90 + 0.25 acceptance -> blended (0.45 + 0.125 = 0.58)
        assert score_low < 0.90
        assert "acceptance rate: 25%" in reason_low
        print(f"  Low acceptance calibrated score downward: 0.90 -> {score_low}")

    print("  PASS")


def main() -> int:
    try:
        test_zero_and_low_history()
        test_calibrated_confidence_movement()
        print("\n" + "=" * 60)
        print("ALL CALIBRATION TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! CALIBRATION TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
