from __future__ import annotations

import ast

from core import config
from core.detectors.base import Detector
from core.models import ErrorType, Fix, Issue

_BLOCK_KEYWORDS = (
    "if ", "elif ", "else", "for ", "while ", "def ", "class ",
    "try", "except", "finally", "with ",
)

_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _fix_missing_colon(lines: list[str], lineno: int) -> bool:
    changed = False
    idx = lineno - 1
    if 0 <= idx < len(lines):
        stripped = lines[idx].rstrip()
        head = stripped.lstrip()
        is_block_header = any(head == kw.strip() or head.startswith(kw) for kw in _BLOCK_KEYWORDS)
        if is_block_header and not stripped.endswith(":") and not stripped.endswith("\\"):
            lines[idx] = stripped + ":"
            changed = True

    # Also sweep all other obvious block headers that are missing colons
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        head = stripped.lstrip()
        is_block_header = any(head == kw.strip() or head.startswith(kw) for kw in _BLOCK_KEYWORDS)
        if is_block_header and not stripped.endswith(":") and not stripped.endswith("\\"):
            lines[i] = stripped + ":"
            changed = True

    return changed


def _fix_tabs(lines: list[str]) -> bool:
    changed = False
    for i, line in enumerate(lines):
        if "\t" in line:
            lines[i] = line.replace("\t", "    ")
            changed = True
    return changed


def _fix_unbalanced_brackets(lines: list[str]) -> bool:
    changed = False
    # 1. First attempt to close unclosed brackets on the specific lines where they were opened
    for i, line in enumerate(lines):
        stack: list[str] = []
        for ch in line:
            if ch in _BRACKET_PAIRS:
                stack.append(_BRACKET_PAIRS[ch])
            elif ch in _BRACKET_PAIRS.values():
                if stack and stack[-1] == ch:
                    stack.pop()
        if stack:
            lines[i] = line + "".join(reversed(stack))
            changed = True

    if changed:
        return True

    # 2. Fallback: file-level bracket balance
    text = "\n".join(lines)
    stack_global: list[str] = []
    for ch in text:
        if ch in _BRACKET_PAIRS:
            stack_global.append(_BRACKET_PAIRS[ch])
        elif ch in _BRACKET_PAIRS.values():
            if stack_global and stack_global[-1] == ch:
                stack_global.pop()
    if stack_global and lines:
        lines[-1] = lines[-1] + "".join(reversed(stack_global))
        return True
    return False


class SyntaxErrorDetector(Detector):
    name = "syntax_error"

    def detect(self, code: str) -> list[Issue]:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return [
                Issue(
                    error_type=ErrorType.SYNTAX_ERROR,
                    line=exc.lineno,
                    message=exc.msg or "invalid syntax",
                    detail=(exc.text or "").strip(),
                    confidence=0.9,
                )
            ]
        return []

    def fix(self, code: str, issues: list[Issue]) -> Fix:
        lines = code.splitlines()
        repairs_applied: list[str] = []

        for _ in range(config.settings.max_fix_attempts):
            try:
                ast.parse("\n".join(lines))
                break  # already valid
            except SyntaxError as exc:
                lineno = exc.lineno or 1
                if _fix_missing_colon(lines, lineno):
                    repairs_applied.append(f"added a missing `:` on line {lineno}")
                    continue
                if "\t" in "\n".join(lines) and _fix_tabs(lines):
                    repairs_applied.append("converted tab characters to spaces")
                    continue
                if _fix_unbalanced_brackets(lines):
                    repairs_applied.append("closed an unbalanced bracket")
                    continue
                break  # nothing more we know how to try

        fixed_code = "\n".join(lines)
        still_broken = False
        try:
            ast.parse(fixed_code)
        except SyntaxError:
            still_broken = True

        if repairs_applied:
            explanation = (
                "Python couldn't even parse this before running it — "
                + "; then ".join(repairs_applied).capitalize()
                + "."
            )
        else:
            explanation = (
                "This has a syntax error the local engine doesn't have a rule for yet. "
                "Connect a cloud LLM in the sidebar for broader coverage."
            )

        if still_broken:
            explanation += " Note: the fix may be incomplete — please review line-by-line."

        return Fix(fixed_code=fixed_code, explanation=explanation, issues_addressed=issues, source="local_engine")
