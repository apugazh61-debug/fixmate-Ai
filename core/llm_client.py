"""
Thin wrapper around the Groq chat-completions API.

Kept isolated from the rest of the engine so the local, offline detectors
never import it directly — if `groq` isn't installed, or no API key is
configured, the app still runs perfectly on the local engine alone.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from core import config

try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False


SYSTEM_PROMPT = """You are FixMate, a precise code-repair assistant.
Given a code snippet (and optionally an error message), you must:
1. Identify the root cause of the bug.
2. Produce a corrected, runnable version of the ENTIRE snippet.
3. Explain the cause in one or two plain-English sentences a junior developer would understand.

Respond ONLY with strict JSON, no markdown fences, matching this shape:
{"fixed_code": "...", "explanation": "...", "error_type": "missing_import|syntax_error|undefined_variable|other"}
"""


@dataclass
class LlmResponse:
    fixed_code: str
    explanation: str
    error_type: str
    raw_latency_s: float


class LlmUnavailable(RuntimeError):
    """Raised when the cloud path can't be used (no key, no package, or API error)."""


def is_available() -> bool:
    return _GROQ_AVAILABLE and config.settings.has_llm


def analyze_and_fix(
    code: str,
    error_message: str = "",
    extra_context: str = "",
    retries: int = 2,
) -> LlmResponse:
    if not _GROQ_AVAILABLE:
        raise LlmUnavailable("The `groq` package isn't installed. Run: pip install groq")
    if not config.settings.has_llm:
        raise LlmUnavailable("No GROQ_API_KEY configured — add one in the sidebar or your environment.")

    client = Groq(api_key=config.settings.groq_api_key)
    prompt_parts = [
        f"CODE:\n{code}\n",
        f"ERROR MESSAGE (if any):\n{error_message or '(none provided)'}\n",
    ]
    if extra_context and extra_context.strip():
        prompt_parts.append(f"ADDITIONAL PROJECT SIBLING CONTEXT:\n{extra_context}\n")

    user_prompt = "\n".join(prompt_parts)

    candidate_models = [
        config.settings.groq_model,
        "llama-3.1-8b-instant",
        "llama-3.1-70b-versatile",
        "llama3-8b-8192",
        "llama3-70b-8192",
        "mixtral-8x7b-32768",
    ]
    models_to_try = list(dict.fromkeys(candidate_models))

    last_err: Exception | None = None
    for model_name in models_to_try:
        for attempt in range(1, retries + 1):
            start = time.time()
            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                )
                latency = time.time() - start
                content = completion.choices[0].message.content.strip()
                content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                
                # Robust JSON parsing
                try:
                    data = json.loads(content)
                except Exception:
                    import re
                    match = re.search(r"\{[\s\S]*\}", content)
                    if match:
                        data = json.loads(match.group(0))
                    else:
                        raise

                return LlmResponse(
                    fixed_code=data.get("fixed_code", code),
                    explanation=data.get("explanation", "No explanation returned."),
                    error_type=data.get("error_type", "other"),
                    raw_latency_s=latency,
                )
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                err_str = str(exc).lower()
                if "model_not_found" in err_str or "does not exist" in err_str or "404" in err_str:
                    break  # try next model in candidate_models
                continue

    raise LlmUnavailable(f"Groq API call failed after {retries} attempts: {last_err}")
