"""
Empirical confidence calibration from real usage history.

Reads past fix acceptance rates from SQLite analytics store per error type.
Blends detector static confidence with empirical user acceptance when >= 10 samples
exist, providing honest, explainable calibrated confidence metrics.
"""

from __future__ import annotations

from pathlib import Path

from core import analytics_store
from core.models import Issue


MIN_CALIBRATION_SAMPLES = 10
CALIBRATION_WINDOW_LIMIT = 50


def calibrated_confidence(
    error_type: str,
    raw_confidence: float,
    min_samples: int = MIN_CALIBRATION_SAMPLES,
    limit: int = CALIBRATION_WINDOW_LIMIT,
    db_path: str | Path | None = None,
) -> tuple[float, str]:
    """Compute calibrated confidence by blending static score with historical acceptance rate.
    
    Returns (calibrated_score, reason_explanation).
    """
    history = analytics_store.get_acceptance_history_for_type(
        error_type=error_type,
        limit=limit,
        db_path=db_path,
    )

    sample_count = len(history)
    if sample_count < min_samples:
        reason = f"static default (insufficient history: {sample_count}/{min_samples} runs)"
        return raw_confidence, reason

    empirical_rate = sum(history) / sample_count
    # Blend static detector prior (50%) with empirical acceptance evidence (50%)
    blended = 0.5 * raw_confidence + 0.5 * empirical_rate
    score = round(max(0.05, min(0.99, blended)), 2)
    reason = f"calibrated from {sample_count} recent runs (acceptance rate: {int(empirical_rate * 100)}%)"

    return score, reason


def calibrate_issues(
    issues: list[Issue],
    db_path: str | Path | None = None,
) -> tuple[list[Issue], list[str]]:
    """Calibrate confidence scores for a list of detected issues in-place.
    
    Returns (issues, calibration_log_messages).
    """
    logs: list[str] = []
    for issue in issues:
        raw = issue.confidence
        etype = issue.error_type.value
        cal_score, explanation = calibrated_confidence(etype, raw, db_path=db_path)
        issue.confidence = cal_score
        logs.append(f"`{etype}`: confidence {raw:.2f} → {cal_score:.2f} ({explanation})")

    return issues, logs
