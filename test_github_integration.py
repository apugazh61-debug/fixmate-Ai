"""
Tests for core/github_integration.py.

Verifies:
1. Parsing of various repo URL formats.
2. Graceful handling of missing token and bad repository format.
3. Handling of 401 Unauthorized, 404 Not Found, and GitHub API errors (mocked).
4. End-to-end successful Pull Request creation workflow (mocked).
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from core import github_integration
from core.models import PipelineStep


def test_repo_slug_parsing():
    print("\n--- Test: Repository URL / slug parsing ---")
    cases = [
        ("https://github.com/apugazh61-debug/fixmate-Ai.git", ("apugazh61-debug", "fixmate-Ai")),
        ("https://github.com/apugazh61-debug/fixmate-Ai", ("apugazh61-debug", "fixmate-Ai")),
        ("http://github.com/owner/repo", ("owner", "repo")),
        ("owner/repo", ("owner", "repo")),
        ("invalid-string", None),
        ("", None),
    ]
    for inp, expected in cases:
        parsed = github_integration.parse_repo_slug(inp)
        assert parsed == expected, f"Expected {expected} for '{inp}', got {parsed}"
    print("  Repository parsing passed for all cases.")
    print("  PASS")


def test_missing_token_and_bad_input():
    print("\n--- Test: Missing token & bad input handling ---")
    # 1. Missing token
    res1 = github_integration.create_pull_request(
        repo_input="owner/repo",
        token="",
        file_path="foo.py",
        fixed_code="x = 1",
    )
    assert res1.success is False
    assert "No GitHub Personal Access Token" in res1.error
    assert len(res1.steps) == 1
    assert res1.steps[0].status == "fail"
    print("  Handled missing token cleanly.")

    # 2. Bad repo string
    res2 = github_integration.create_pull_request(
        repo_input="just-a-name-no-slash",
        token="ghp_fake_token",
        file_path="foo.py",
        fixed_code="x = 1",
    )
    assert res2.success is False
    assert "Invalid GitHub repository format" in res2.error
    print("  Handled invalid repo format cleanly.")
    print("  PASS")


def test_api_errors_mocked():
    print("\n--- Test: GitHub API error responses (mocked) ---")
    mock_session = MagicMock()

    # 1. 401 Unauthorized
    mock_r401 = MagicMock()
    mock_r401.status_code = 401
    mock_r401.ok = False
    mock_session.get.return_value = mock_r401

    with patch("requests.Session", return_value=mock_session):
        res401 = github_integration.create_pull_request(
            repo_input="owner/repo",
            token="ghp_invalid_token",
            file_path="main.py",
            fixed_code="print('ok')",
        )
        assert res401.success is False
        assert "401 Bad Credentials" in res401.error
        print("  Handled 401 Bad Credentials.")

    # 2. 404 Repo Not Found
    mock_r404 = MagicMock()
    mock_r404.status_code = 404
    mock_r404.ok = False
    mock_session.get.return_value = mock_r404

    with patch("requests.Session", return_value=mock_session):
        res404 = github_integration.create_pull_request(
            repo_input="owner/private-repo",
            token="ghp_token",
            file_path="main.py",
            fixed_code="print('ok')",
        )
        assert res404.success is False
        assert "404" in res404.error
        print("  Handled 404 Repo Not Found.")

    print("  PASS")


def test_successful_pr_flow_mocked():
    print("\n--- Test: Successful PR Creation Flow (mocked) ---")
    mock_session = MagicMock()

    # 1. repo info (default branch = main)
    mock_repo = MagicMock(status_code=200, ok=True)
    mock_repo.json.return_value = {"default_branch": "main"}

    # 2. head ref
    mock_ref = MagicMock(status_code=200, ok=True)
    mock_ref.json.return_value = {"object": {"sha": "base123sha"}}

    # 3. branch creation
    mock_branch = MagicMock(status_code=201, ok=True)
    mock_branch.json.return_value = {"ref": "refs/heads/fixmate/auto-fix-test"}

    # 4. existing file check (404 = new file)
    mock_file_get = MagicMock(status_code=404, ok=False)

    # 5. commit file
    mock_commit = MagicMock(status_code=201, ok=True)
    mock_commit.json.return_value = {"content": {"sha": "newfilesha"}}

    # 6. create PR
    mock_pr = MagicMock(status_code=201, ok=True)
    mock_pr.json.return_value = {
        "html_url": "https://github.com/owner/repo/pull/1",
        "number": 1,
    }

    mock_session.get.side_effect = [mock_repo, mock_ref, mock_file_get]
    mock_session.post.side_effect = [mock_branch, mock_pr]
    mock_session.put.side_effect = [mock_commit]

    with patch("requests.Session", return_value=mock_session):
        res = github_integration.create_pull_request(
            repo_input="owner/repo",
            token="ghp_valid_token_12345",
            file_path="src/calc.py",
            fixed_code="def calc(x): return x + 1",
            explanation="Fixed syntax and undefined variable",
            trace=[PipelineStep("Detect", "ok", "Fixed 2 bugs")],
            branch_name="fixmate/auto-fix-test",
        )
        assert res.success is True
        assert res.pr_url == "https://github.com/owner/repo/pull/1"
        assert res.pr_number == 1
        assert res.branch_name == "fixmate/auto-fix-test"
        assert len(res.steps) == 4
        print(f"  Successfully opened PR #{res.pr_number}: {res.pr_url}")

    print("  PASS")


def main() -> int:
    try:
        test_repo_slug_parsing()
        test_missing_token_and_bad_input()
        test_api_errors_mocked()
        test_successful_pr_flow_mocked()
        print("\n" + "=" * 60)
        print("ALL GITHUB INTEGRATION TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! GITHUB INTEGRATION TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
