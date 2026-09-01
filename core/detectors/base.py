from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import Fix, Issue


class Detector(ABC):
    """Contract every error-class detector must satisfy."""

    name: str = "base"

    @abstractmethod
    def detect(self, code: str) -> list[Issue]:
        """Return every issue of this detector's class found in `code`."""

    @abstractmethod
    def fix(self, code: str, issues: list[Issue]) -> Fix:
        """Given the issues this detector found, return a proposed fix."""
