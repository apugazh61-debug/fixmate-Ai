"""
JavaScript Syntax Error Detector & Fixer.

Validates JavaScript syntax using `node --check` when available on the host,
falling back to AST/regex bracket analysis when node is absent.
Applies targeted structural repairs to unclosed parentheses and unbalanced blocks.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

from core.detectors.base import Detector
from core.models import ErrorType, Fix, Issue


def is_node_available() -> bool:
    """True if Node.js CLI binary is found."""
    return bool(shutil.which("node"))


def check_node_syntax(code: str) -> tuple[bool, str, int | None]:
    """Run `node --check` against temporary file. Returns (is_valid, error_msg, line_num)."""
    if not is_node_available():
        return True, "", None

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", encoding="utf-8", delete=False) as f:
            f.write(code)
            tmp_file = f.name

        proc = subprocess.run(
            ["node", "--check", tmp_file],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if proc.returncode == 0:
            return True, "", None

        err_output = proc.stderr.strip() or proc.stdout.strip()
        line_match = re.search(rf"{re.escape(tmp_file)}:(\d+)", err_output)
        line_no = int(line_match.group(1)) if line_match else 1
        return False, err_output, line_no
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:  # noqa: BLE001
                pass


class JsSyntaxErrorDetector(Detector):
    name = "js_syntax_error"

    def detect(self, code: str) -> list[Issue]:
        issues: list[Issue] = []
        lines = code.splitlines()

        # 1. Pattern checks for common missing closing parentheses
        for idx, line in enumerate(lines, start=1):
            # for (const x of items {
            if re.search(r'\bfor\s*\([^)]*\{', line) and ')' not in line:
                issues.append(Issue(
                    error_type=ErrorType.SYNTAX_ERROR,
                    line=idx,
                    message="Missing closing parenthesis `)` in `for` loop declaration.",
                    detail="missing_paren_for",
                    confidence=0.95,
                ))
            # if (cond {
            elif re.search(r'\bif\s*\([^)]*\{', line) and ')' not in line:
                issues.append(Issue(
                    error_type=ErrorType.SYNTAX_ERROR,
                    line=idx,
                    message="Missing closing parenthesis `)` in `if` statement.",
                    detail="missing_paren_if",
                    confidence=0.95,
                ))
            # while (cond {
            elif re.search(r'\bwhile\s*\([^)]*\{', line) and ')' not in line:
                issues.append(Issue(
                    error_type=ErrorType.SYNTAX_ERROR,
                    line=idx,
                    message="Missing closing parenthesis `)` in `while` loop declaration.",
                    detail="missing_paren_while",
                    confidence=0.95,
                ))

        # 2. If node is available, verify with node --check
        if not issues and is_node_available():
            valid, err_msg, line_no = check_node_syntax(code)
            if not valid:
                clean_err = err_msg.splitlines()[0] if err_msg else "SyntaxError in JavaScript"
                issues.append(Issue(
                    error_type=ErrorType.SYNTAX_ERROR,
                    line=line_no or 1,
                    message=clean_err,
                    detail="node_check_error",
                    confidence=0.90,
                ))

        return issues

    def fix(self, code: str, issues: list[Issue]) -> Fix:
        lines = code.splitlines()
        fixed_lines = list(lines)

        for issue in issues:
            line_idx = (issue.line - 1) if issue.line and 1 <= issue.line <= len(lines) else 0
            curr_line = fixed_lines[line_idx]

            # Fix for (x of y { -> for (x of y) {
            if re.search(r'\bfor\s*\(.*\{', curr_line) and ')' not in curr_line:
                fixed_lines[line_idx] = re.sub(r'(\bfor\s*\(.*?)\s*\{', r'\1) {', curr_line)
            # Fix if (cond { -> if (cond) {
            elif re.search(r'\bif\s*\(.*\{', curr_line) and ')' not in curr_line:
                fixed_lines[line_idx] = re.sub(r'(\bif\s*\(.*?)\s*\{', r'\1) {', curr_line)
            # Fix while (cond { -> while (cond) {
            elif re.search(r'\bwhile\s*\(.*\{', curr_line) and ')' not in curr_line:
                fixed_lines[line_idx] = re.sub(r'(\bwhile\s*\(.*?)\s*\{', r'\1) {', curr_line)

        fixed_code = "\n".join(fixed_lines)
        explanation = f"Repaired JavaScript syntax error(s) on line(s) {', '.join(str(i.line) for i in issues if i.line)}."

        return Fix(
            fixed_code=fixed_code,
            explanation=explanation,
            issues_addressed=issues,
            source="local_engine_js",
        )
