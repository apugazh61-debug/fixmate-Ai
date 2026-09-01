"""
Tests for core/analytics_store.py.

Verifies:
1. Lazy DB initialization.
2. Handling of empty database without throwing exceptions.
3. Correct insertion of AnalysisResult records.
4. Calculation of summary metrics, error frequency, and top recurring files.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from core import analytics_store
from core.models import AnalysisResult, ErrorType, Issue


def test_empty_db_queries():
    print("\n--- Test: Empty DB queries ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_empty.db"

        stats = analytics_store.get_summary_stats(db_path=db_path)
        assert stats["total_runs"] == 0
        assert stats["verified_count"] == 0
        assert stats["verification_rate"] == 0.0

        freq = analytics_store.get_error_frequency(db_path=db_path)
        assert freq == {}

        top = analytics_store.get_top_recurring_files(db_path=db_path)
        assert top == []

        hist = analytics_store.get_recent_history(db_path=db_path)
        assert hist == []

        print("  Empty DB handled cleanly across all query functions.")

    print("  PASS")


def test_record_and_aggregations():
    print("\n--- Test: Record insertions and aggregations ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_analytics.db"

        # Record 1: syntax error in utils.py (verified, local)
        r1 = AnalysisResult(
            original_code="def f():",
            fixed_code="def f(): pass",
            issues=[Issue(error_type=ErrorType.SYNTAX_ERROR, line=1, message="expected ':'")],
            explanation="Added colon",
            verified=True,
            attempts=1,
            source="local_engine",
        )
        analytics_store.record_result(r1, repo_name="myorg/myrepo", file_path="src/utils.py", db_path=db_path)

        # Record 2: missing import in utils.py (verified, local)
        r2 = AnalysisResult(
            original_code="math.pi",
            fixed_code="import math\nmath.pi",
            issues=[Issue(error_type=ErrorType.MISSING_IMPORT, line=1, message="math missing")],
            explanation="Added import",
            verified=True,
            attempts=1,
            source="local_engine",
        )
        analytics_store.record_result(r2, repo_name="myorg/myrepo", file_path="src/utils.py", db_path=db_path)

        # Record 3: logic bug in calc.py (not verified, groq_llm)
        r3 = AnalysisResult(
            original_code="x = None",
            fixed_code="x = 10",
            issues=[Issue(error_type=ErrorType.UNKNOWN, line=1, message="logic bug")],
            explanation="Fixed logic",
            verified=False,
            attempts=3,
            source="groq_llm",
        )
        analytics_store.record_result(r3, repo_name="myorg/myrepo", file_path="src/calc.py", db_path=db_path)

        # Verify summary stats
        stats = analytics_store.get_summary_stats(db_path=db_path)
        assert stats["total_runs"] == 3
        assert stats["verified_count"] == 2
        assert stats["local_runs"] == 2
        assert stats["groq_runs"] == 1
        assert stats["verification_rate"] == 66.7
        print(f"  Summary stats verified: {stats}")

        # Verify error frequency
        freq = analytics_store.get_error_frequency(db_path=db_path)
        assert freq.get("syntax_error") == 1
        assert freq.get("missing_import") == 1
        assert freq.get("unknown") == 1
        print(f"  Error frequency verified: {freq}")

        # Verify top recurring files
        top = analytics_store.get_top_recurring_files(db_path=db_path)
        assert len(top) == 2
        assert top[0]["file_path"] == "src/utils.py"
        assert top[0]["count"] == 2
        assert top[1]["file_path"] == "src/calc.py"
        assert top[1]["count"] == 1
        print(f"  Top recurring files verified: {top}")

        # Verify history
        hist = analytics_store.get_recent_history(db_path=db_path)
        assert len(hist) == 3
        assert hist[0]["file_path"] == "src/calc.py"
        assert hist[0]["verified"] is False
        print(f"  History length verified: {len(hist)}")

    print("  PASS")


def main() -> int:
    try:
        test_empty_db_queries()
        test_record_and_aggregations()
        print("\n" + "=" * 60)
        print("ALL ANALYTICS STORE TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! ANALYTICS STORE TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
