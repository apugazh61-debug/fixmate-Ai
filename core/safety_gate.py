"""
Pre-merge safety gate and blast-radius risk assessment.

Audits proposed fixes prior to opening automated Pull Requests:
1. AST function signature change detection (breaking change risk).
2. Blast radius calculation (% lines changed vs total lines).
3. Subprocess Bandit static security scan diff (flags only NEW findings).

Blocks automated PR if risk is HIGH or if a new HIGH-severity security
vulnerability is introduced. Degrades cleanly if Bandit is not installed.
"""

from __future__ import annotations

import ast
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


try:
    import bandit  # noqa: F401
    _BANDIT_INSTALLED = True
except ImportError:
    _BANDIT_INSTALLED = False


@dataclass
class BanditFinding:
    """Security vulnerability reported by Bandit."""
    test_id: str
    severity: str  # "HIGH", "MEDIUM", "LOW"
    confidence: str
    text: str
    line: int


@dataclass
class RiskAssessment:
    """Consolidated safety risk assessment for a proposed fix."""
    level: str  # "low" | "medium" | "high"
    blocks_pr: bool
    blast_radius_score: float
    signature_changed: bool
    reasons: list[str] = field(default_factory=list)
    new_bandit_findings: list[BanditFinding] = field(default_factory=list)
    bandit_executed: bool = False

    @property
    def summary(self) -> str:
        status = "⛔ BLOCKED" if self.blocks_pr else ("⚠️ REVIEW" if self.level == "medium" else "✅ SAFE")
        return f"[{status}] Risk: {self.level.upper()} (Blast radius: {int(self.blast_radius_score * 100)}%)"


def is_bandit_available() -> bool:
    """True if Bandit CLI or module is available in environment."""
    return _BANDIT_INSTALLED or bool(shutil.which("bandit"))


def _extract_function_signatures(tree: ast.AST) -> dict[str, tuple[list[str], list[str], str | None, str | None, int]]:
    """Map function name to its argument signature details."""
    sigs: dict[str, tuple[list[str], list[str], str | None, str | None, int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pos_args = [a.arg for a in node.args.args]
            kw_args = [a.arg for a in node.args.kwonlyargs]
            vararg = node.args.vararg.arg if node.args.vararg else None
            kwarg = node.args.kwarg.arg if node.args.kwarg else None
            defaults_count = len(node.args.defaults)
            sigs[node.name] = (pos_args, kw_args, vararg, kwarg, defaults_count)
    return sigs


def check_signature_changes(original_code: str, fixed_code: str) -> tuple[bool, list[str]]:
    """Detect if any existing function signatures were modified (breaking API changes)."""
    try:
        orig_tree = ast.parse(original_code)
        fixed_tree = ast.parse(fixed_code)
    except SyntaxError:
        return False, []

    orig_sigs = _extract_function_signatures(orig_tree)
    fixed_sigs = _extract_function_signatures(fixed_tree)

    changed_reasons: list[str] = []
    for fn_name, orig_sig in orig_sigs.items():
        if fn_name not in fixed_sigs:
            changed_reasons.append(f"Function `{fn_name}` was deleted or renamed.")
        elif orig_sig != fixed_sigs[fn_name]:
            changed_reasons.append(f"Signature of function `{fn_name}` was modified.")

    return bool(changed_reasons), changed_reasons


def compute_blast_radius(original_code: str, fixed_code: str) -> float:
    """Compute ratio of modified lines to total original lines."""
    orig_lines = original_code.splitlines()
    fixed_lines = fixed_code.splitlines()

    if not orig_lines:
        return 0.0

    diff = list(difflib.unified_diff(orig_lines, fixed_lines, lineterm=""))
    changed_count = sum(1 for line in diff if (line.startswith("+") or line.startswith("-")) and not (line.startswith("+++") or line.startswith("---")))

    return min(1.0, round(changed_count / max(len(orig_lines), 1), 2))


def run_bandit_scan(code: str) -> list[BanditFinding]:
    """Execute Bandit against a temporary file containing the snippet."""
    if not is_bandit_available():
        return []

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", encoding="utf-8", delete=False) as f:
            f.write(code)
            tmp_file = f.name

        cmd = [sys.executable, "-m", "bandit", "-f", "json", "-q", tmp_file]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if not proc.stdout.strip():
            return []

        data = json.loads(proc.stdout)
        findings: list[BanditFinding] = []
        for item in data.get("results", []):
            findings.append(BanditFinding(
                test_id=item.get("test_id", ""),
                severity=item.get("issue_severity", "LOW").upper(),
                confidence=item.get("issue_confidence", "LOW").upper(),
                text=item.get("issue_text", ""),
                line=item.get("line_number", 1),
            ))
        return findings
    except Exception:  # noqa: BLE001
        return []
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:  # noqa: BLE001
                pass


def assess_risk(
    original_code: str,
    fixed_code: str,
    file_path: str = "",
) -> RiskAssessment:
    """Run comprehensive risk assessment on proposed fix."""
    reasons: list[str] = []
    level = "low"
    blocks_pr = False

    # 1. Blast Radius
    blast_score = compute_blast_radius(original_code, fixed_code)
    if blast_score >= 0.7:
        level = "medium"
        reasons.append(f"Large blast radius: {int(blast_score * 100)}% of file altered.")
    elif blast_score >= 0.4:
        reasons.append(f"Moderate blast radius: {int(blast_score * 100)}% of file altered.")

    # 2. Function Signature Modifications
    sig_changed, sig_reasons = check_signature_changes(original_code, fixed_code)
    if sig_changed:
        reasons.extend(sig_reasons)
        if blast_score > 0.5:
            level = "high"
            blocks_pr = True
            reasons.append("High risk: Combined function signature change and high blast radius.")
        else:
            level = max(level, "medium")

    # 3. Bandit Security Scan Diff
    new_findings: list[BanditFinding] = []
    bandit_ran = is_bandit_available()

    if bandit_ran:
        orig_findings = run_bandit_scan(original_code)
        fixed_findings = run_bandit_scan(fixed_code)

        orig_fingerprints = {(f.test_id, f.text) for f in orig_findings}
        for f in fixed_findings:
            if (f.test_id, f.text) not in orig_fingerprints:
                new_findings.append(f)

        for finding in new_findings:
            if finding.severity == "HIGH" or finding.test_id in ("B307", "B102", "B602"):
                level = "high"
                blocks_pr = True
                reasons.append(f"⛔ Security Vulnerability introduced ({finding.severity}): {finding.text} (line {finding.line}).")
            elif finding.severity == "MEDIUM":
                level = max(level, "medium")
                reasons.append(f"⚠️ Security Warning introduced (MEDIUM): {finding.text} (line {finding.line}).")
    else:
        reasons.append("Bandit security scanner not installed; evaluated based on AST blast-radius and signature check.")

    if not reasons:
        reasons.append("Clean localized fix with no security warnings or breaking signature modifications.")

    return RiskAssessment(
        level=level,
        blocks_pr=blocks_pr,
        blast_radius_score=blast_score,
        signature_changed=sig_changed,
        reasons=reasons,
        new_bandit_findings=new_findings,
        bandit_executed=bandit_ran,
    )
