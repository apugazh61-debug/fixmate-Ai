"""
GitHub Auto-PR integration using the GitHub REST API via `requests`.

Creates a new branch, commits the fixed file, and opens a Pull Request back
to the default branch with auto-generated release notes and pipeline trace.

Degrades cleanly with structured PipelineStep / PrResult on missing tokens,
auth failures, repo not found, or rate limits. Tokens are never logged or
saved to disk.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field

import requests

from core.models import PipelineStep


GITHUB_API_BASE = "https://api.github.com"


@dataclass
class PrResult:
    """Outcome of attempting to open an automated Pull Request."""
    success: bool
    pr_url: str = ""
    pr_number: int | None = None
    branch_name: str = ""
    error: str = ""
    steps: list[PipelineStep] = field(default_factory=list)


def parse_repo_slug(repo_input: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from URL or 'owner/repo' format."""
    clean = repo_input.strip().rstrip("/")
    clean = clean.removesuffix(".git")

    # Match https://github.com/owner/repo or http://github.com/owner/repo
    m_url = re.match(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)$", clean, re.IGNORECASE)
    if m_url:
        return m_url.group(1), m_url.group(2)

    # Match owner/repo directly
    m_slug = re.match(r"^([^/\s]+)/([^/\s]+)$", clean)
    if m_slug:
        return m_slug.group(1), m_slug.group(2)

    return None


def format_pr_body(
    file_path: str,
    explanation: str,
    trace: list[PipelineStep] | None = None,
) -> str:
    """Build a rich, structured Markdown PR description."""
    body_lines = [
        "## 🛠️ FixMate AI Automated Fix",
        "",
        f"**Target File:** `{file_path}`",
        "",
        "### 📝 Summary of Changes",
        explanation or "Automated repair applied by FixMate AI.",
        "",
    ]

    if trace:
        body_lines.append("### 🔍 Pipeline Trace")
        body_lines.append("| Status | Step | Detail |")
        body_lines.append("|:---:|:---|:---|")
        icon_map = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}
        for step in trace:
            icon = icon_map.get(step.status, "•")
            clean_detail = step.detail.replace("\n", " ").replace("|", "\\|")
            body_lines.append(f"| {icon} | **{step.name}** | {clean_detail} |")
        body_lines.append("")

    body_lines.extend([
        "---",
        "*Created automatically by [FixMate AI](https://github.com/apugazh61-debug/fixmate-Ai) — Developer Tools Track.*",
    ])
    return "\n".join(body_lines)


def create_pull_request(
    repo_input: str,
    token: str,
    file_path: str,
    fixed_code: str,
    explanation: str = "",
    trace: list[PipelineStep] | None = None,
    branch_name: str | None = None,
) -> PrResult:
    """Execute the GitHub PR flow: branch -> commit -> open PR.
    
    Never raises uncaught exceptions.
    """
    steps: list[PipelineStep] = []

    if not token or not token.strip():
        step = PipelineStep("GitHub Auth", "fail", "No GitHub Personal Access Token provided.")
        steps.append(step)
        return PrResult(success=False, error=step.detail, steps=steps)

    parsed = parse_repo_slug(repo_input)
    if not parsed:
        step = PipelineStep(
            "Validate Repo", "fail",
            f"Invalid GitHub repository format: '{repo_input}'. Use 'owner/repo' or 'https://github.com/owner/repo'.",
        )
        steps.append(step)
        return PrResult(success=False, error=step.detail, steps=steps)

    owner, repo = parsed
    clean_file_path = file_path.strip().lstrip("/").replace("\\", "/")
    if not clean_file_path:
        clean_file_path = "fixed_code.py"

    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FixMate-AI",
    }

    session = requests.Session()
    session.headers.update(headers)

    # 1. Fetch Repository Info & Default Branch
    try:
        r_repo = session.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", timeout=10)
        if r_repo.status_code == 401:
            step = PipelineStep("GitHub Auth", "fail", "Authentication failed (401 Bad Credentials). Check your token.")
            steps.append(step)
            return PrResult(success=False, error=step.detail, steps=steps)
        if r_repo.status_code == 404:
            step = PipelineStep("Fetch Repo", "fail", f"Repository '{owner}/{repo}' not found or token lacks access (404).")
            steps.append(step)
            return PrResult(success=False, error=step.detail, steps=steps)
        if not r_repo.ok:
            step = PipelineStep("Fetch Repo", "fail", f"GitHub API error ({r_repo.status_code}): {r_repo.text}")
            steps.append(step)
            return PrResult(success=False, error=step.detail, steps=steps)

        repo_info = r_repo.json()
        default_branch = repo_info.get("default_branch", "main")
        steps.append(PipelineStep("Fetch Repo", "ok", f"Connected to {owner}/{repo} (default branch: `{default_branch}`)."))

        # 2. Get latest commit SHA on default branch
        r_ref = session.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{default_branch}", timeout=10)
        if not r_ref.ok:
            step = PipelineStep("Branch Ref", "fail", f"Failed to get `{default_branch}` head commit ({r_ref.status_code}): {r_ref.text}")
            steps.append(step)
            return PrResult(success=False, error=step.detail, steps=steps)

        base_sha = r_ref.json()["object"]["sha"]

        # 3. Create new branch
        target_branch = branch_name or f"fixmate/auto-fix-{int(time.time())}"
        r_branch = session.post(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{target_branch}", "sha": base_sha},
            timeout=10,
        )
        if not r_branch.ok:
            step = PipelineStep("Create Branch", "fail", f"Failed to create branch `{target_branch}` ({r_branch.status_code}): {r_branch.text}")
            steps.append(step)
            return PrResult(success=False, error=step.detail, steps=steps)

        steps.append(PipelineStep("Create Branch", "ok", f"Created branch `{target_branch}` from `{default_branch}`."))

        # 4. Check if file already exists in branch to get its SHA
        r_file = session.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{clean_file_path}",
            params={"ref": target_branch},
            timeout=10,
        )
        file_sha: str | None = None
        if r_file.status_code == 200:
            file_sha = r_file.json().get("sha")

        # 5. Commit fixed code
        b64_content = base64.b64encode(fixed_code.encode("utf-8")).decode("ascii")
        commit_payload: dict[str, str] = {
            "message": f"FixMate AI: automated fix for {clean_file_path}",
            "content": b64_content,
            "branch": target_branch,
        }
        if file_sha:
            commit_payload["sha"] = file_sha

        r_commit = session.put(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{clean_file_path}",
            json=commit_payload,
            timeout=10,
        )
        if not r_commit.ok:
            step = PipelineStep("Commit File", "fail", f"Failed to commit `{clean_file_path}` ({r_commit.status_code}): {r_commit.text}")
            steps.append(step)
            return PrResult(success=False, error=step.detail, steps=steps)

        steps.append(PipelineStep("Commit File", "ok", f"Committed fixed `{clean_file_path}` to `{target_branch}`."))

        # 6. Open Pull Request
        pr_body = format_pr_body(clean_file_path, explanation, trace)
        r_pr = session.post(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
            json={
                "title": f"🛠️ FixMate AI: Fix for {clean_file_path}",
                "head": target_branch,
                "base": default_branch,
                "body": pr_body,
            },
            timeout=10,
        )
        if not r_pr.ok:
            step = PipelineStep("Open PR", "fail", f"Failed to open PR ({r_pr.status_code}): {r_pr.text}")
            steps.append(step)
            return PrResult(success=False, error=step.detail, steps=steps)

        pr_data = r_pr.json()
        pr_url = pr_data.get("html_url", "")
        pr_number = pr_data.get("number")
        steps.append(PipelineStep("Open PR", "ok", f"Successfully opened PR #{pr_number}: {pr_url}"))

        return PrResult(
            success=True,
            pr_url=pr_url,
            pr_number=pr_number,
            branch_name=target_branch,
            steps=steps,
        )

    except requests.RequestException as exc:
        step = PipelineStep("GitHub API", "fail", f"Network or connection error: {exc}")
        steps.append(step)
        return PrResult(success=False, error=step.detail, steps=steps)
    except Exception as exc:  # noqa: BLE001
        step = PipelineStep("GitHub API", "fail", f"Unexpected error: {exc}")
        steps.append(step)
        return PrResult(success=False, error=step.detail, steps=steps)
