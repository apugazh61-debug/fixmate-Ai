"""
Benchmark subset verification test for FixMate AI.
Runs a 10-snippet random sample across all 3 conditions to verify directional consistency.
"""

from __future__ import annotations

import random
from pathlib import Path

from benchmark.corpus import get_corpus
from benchmark.run_benchmark import (
    evaluate_condition_hybrid,
    evaluate_condition_local_only,
    evaluate_condition_naive,
)

def run_subset_check():
    print("--- 1. Checking benchmark timestamp & consistency ---")
    results_json = Path("benchmark/results/results.json")
    results_md = Path("benchmark/results.md")

    assert results_json.exists(), "results.json is missing"
    assert results_md.exists(), "results.md is missing"

    t_json = results_json.stat().st_mtime
    t_md = results_md.stat().st_mtime
    print(f"  results.json mod time: {t_json}")
    print(f"  results.md mod time:   {t_md}")
    assert abs(t_json - t_md) < 60, "results.json and results.md timestamps diverge"
    print("  Timestamps are consistent.")

    print("\n--- 2. Running 10-snippet random subset benchmark ---")
    random.seed(12345)
    corpus = get_corpus()
    sample = random.sample(corpus, 10)

    res_local = evaluate_condition_local_only(sample)
    res_hybrid = evaluate_condition_hybrid(sample)
    res_naive = evaluate_condition_naive(sample)

    local_clean = sum(1 for r in res_local if r.verified_clean)
    hybrid_clean = sum(1 for r in res_hybrid if r.verified_clean)
    naive_clean = sum(1 for r in res_naive if r.verified_clean)

    print(f"  Subset Local Clean Rate:  {local_clean}/10 ({local_clean*10}%)")
    print(f"  Subset Hybrid Clean Rate: {hybrid_clean}/10 ({hybrid_clean*10}%)")
    print(f"  Subset Naive Clean Rate:  {naive_clean}/10 ({naive_clean*10}%)")

    # Assert condition ii & i >= condition iii
    assert hybrid_clean >= naive_clean, f"Anomaly: Naive ({naive_clean}) beat Hybrid ({hybrid_clean})"
    assert local_clean >= naive_clean, f"Anomaly: Naive ({naive_clean}) beat Local ({local_clean})"
    print("  Directional consistency confirmed: FixMate pipeline outperforms naive baseline.")


if __name__ == "__main__":
    run_subset_check()
