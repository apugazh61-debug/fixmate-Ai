"""Pluggable error detectors. Each detector owns one error class end-to-end:
detect it, explain it, and propose a fix. New error classes can be added by
dropping a new module in this package and registering it in core/engine.py.
"""

from .base import Detector
from .missing_import import MissingImportDetector
from .syntax_error import SyntaxErrorDetector
from .undefined_variable import UndefinedVariableDetector

__all__ = [
    "Detector",
    "MissingImportDetector",
    "SyntaxErrorDetector",
    "UndefinedVariableDetector",
]
