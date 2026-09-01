"""
Shared data structures passed between pipeline stages.

Keeping these as typed dataclasses (rather than raw dicts) means every
stage of the pipeline — detector, fixer, verifier, explainer — agrees on
one contract, and the UI layer never has to guess at field names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ErrorType(str, Enum):
    MISSING_IMPORT = "missing_import"
    SYNTAX_ERROR = "syntax_error"
    UNDEFINED_VARIABLE = "undefined_variable"
    UNKNOWN = "unknown"
    NONE = "none"


@dataclass
class Issue:
    """A single detected problem in the source code."""
    error_type: ErrorType
    line: int | None
    message: str
    detail: str = ""
    confidence: float = 1.0


@dataclass
class Fix:
    """A proposed fix for one or more issues."""
    fixed_code: str
    explanation: str
    issues_addressed: list[Issue] = field(default_factory=list)
    source: str = "local_engine"  # "local_engine" | "groq_llm"


@dataclass
class PipelineStep:
    """One step of the agent trace, shown live in the UI."""
    name: str
    status: str  # "ok" | "warn" | "fail" | "info"
    detail: str


@dataclass
class AnalysisResult:
    original_code: str
    fixed_code: str
    issues: list[Issue]
    explanation: str
    verified: bool
    attempts: int
    trace: list[PipelineStep] = field(default_factory=list)
    source: str = "local_engine"
