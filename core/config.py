"""
Central configuration for FixMate AI.

Reads runtime settings from environment variables so the same codebase
works locally, in CI, and when deployed (e.g. Streamlit Cloud secrets).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None
    groq_model: str
    max_fix_attempts: int
    app_name: str = "FixMate AI"

    @property
    def has_llm(self) -> bool:
        """True when a cloud LLM key is configured."""
        return bool(self.groq_api_key)


def load_settings() -> Settings:
    return Settings(
        groq_api_key=os.environ.get("GROQ_API_KEY"),
        groq_model=os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
        max_fix_attempts=int(os.environ.get("FIXMATE_MAX_ATTEMPTS", "3")),
    )


settings = load_settings()
