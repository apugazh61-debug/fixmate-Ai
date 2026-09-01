"""
Tests for benchmark/corpus.py.

Verifies:
1. Total corpus size >= 60 items.
2. Integrity of all corpus entries (non-empty fields, parseable ground truth).
3. No duplicate IDs or snippet contents.
4. Class balance report across categories.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter

from benchmark.corpus import CORPUS, get_corpus


def test_corpus_size_and_uniqueness():
    print("\n--- Test: Corpus size and uniqueness ---")
    total = len(CORPUS)
    print(f"  Total snippets in corpus: {total}")
    assert total >= 60, f"Corpus size {total} is less than required 60."

    # Check ID uniqueness
    ids = [item.id for item in CORPUS]
    id_counts = Counter(ids)
    duplicates = [i for i, c in id_counts.items() if c > 1]
    assert not duplicates, f"Found duplicate IDs: {duplicates}"

    # Check snippet uniqueness
    snippets = [item.broken_code.strip() for item in CORPUS]
    assert len(snippets) == len(set(snippets)), "Found duplicate broken_code snippets in corpus."
    print("  All corpus entries have unique IDs and distinct code snippets.")
    print("  PASS")


def test_entry_integrity_and_parseability():
    print("\n--- Test: Entry integrity & ground truth validation ---")
    for item in CORPUS:
        assert item.id, "Missing ID"
        assert item.language in ("python", "javascript"), f"Unknown language: {item.language}"
        assert item.error_type in ("missing_import", "syntax_error", "undefined_variable", "out_of_distribution"), f"Unknown error_type: {item.error_type}"
        assert item.broken_code.strip(), f"Empty broken_code for {item.id}"
        assert item.ground_truth_fix.strip(), f"Empty ground_truth_fix for {item.id}"

        # If Python, ground truth fix must parse cleanly
        if item.language == "python":
            try:
                ast.parse(item.ground_truth_fix)
            except SyntaxError as e:
                raise AssertionError(f"Ground truth fix for {item.id} failed to parse: {e}") from e

    print("  All entries passed field validation and Python ground truth fixes parse cleanly.")
    print("  PASS")


def test_class_balance_report():
    print("\n--- Test: Class balance summary ---")
    by_lang = Counter(item.language for item in CORPUS)
    by_type = Counter(f"{item.language} · {item.error_type}" for item in CORPUS)

    print("  Language distribution:")
    for lang, count in by_lang.items():
        print(f"    - {lang}: {count} snippets")

    print("  Category breakdown:")
    for category, count in sorted(by_type.items()):
        print(f"    - {category}: {count} snippets")

    assert by_lang["python"] >= 50
    assert by_lang["javascript"] >= 10
    print("  PASS")


def main() -> int:
    try:
        test_corpus_size_and_uniqueness()
        test_entry_integrity_and_parseability()
        test_class_balance_report()
        print("\n" + "=" * 60)
        print("ALL BENCHMARK CORPUS TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! BENCHMARK CORPUS TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
