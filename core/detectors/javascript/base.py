"""
Base detector interface for JavaScript detectors.

Re-exports the core Detector abstract base class for JavaScript detector implementations.
"""

from __future__ import annotations

from core.detectors.base import Detector

__all__ = ["Detector"]
