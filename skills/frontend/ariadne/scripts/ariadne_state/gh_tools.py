"""GitHub CLI helpers for Ariadne v2."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from . import git_tools, io


class GhError(RuntimeError):
    """Raised when GitHub CLI operations fail."""


def _run_gh(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_gh_json(root: Path, *args: str) -> Any:
    completed = _run_gh(root, *args)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown gh error"
        raise GhError(detail)
    try:
        return io.read_json_payload(completed.stdout)
    except ValueError as exc:
        raise GhError(str(exc)) from exc


def ensure_gh_ready(root: Path) -> None:
    version = _run_gh(root, "--version")
    if version.returncode != 0:
        raise GhError("GitHub CLI `gh` is required for Ariadne remote PR tracking.")
    auth = _run_gh(root, "auth", "status")
    if auth.returncode != 0:
        detail = auth.stderr.strip() or auth.stdout.strip() or "GitHub CLI authentication failed."
        raise GhError(detail)


def resolve_remote_context(root: Path, *, repo: str | None, base_branch: str | None) -> dict[str, str]:
    ensure_gh_ready(root)
    repo_slug = repo or git_tools.infer_github_repo(root)
    if not repo_slug:
        raise GhError("Could not infer GitHub repo slug. Pass `--repo` or configure an origin remote.")
    repo_payload = _run_gh_json(root, "api", f"repos/{repo_slug}")
    if not isinstance(repo_payload, dict):
        raise GhError(f"Expected repository object from GitHub for {repo_slug}.")
    resolved_base_branch = base_branch or str(repo_payload.get("default_branch") or "").strip()
    if not resolved_base_branch:
        raise GhError(f"Could not determine default branch for {repo_slug}.")
    return {
        "repo": repo_slug,
        "base_branch": resolved_base_branch,
    }


def list_merged_prs(
    root: Path,
    *,
    repo: str,
    base_branch: str,
    since_pr: int | None,
    until_pr: int | None,
) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "state": "closed",
            "base": base_branch,
            "per_page": 100,
        }
    )
    payload = _run_gh_json(root, "api", f"repos/{repo}/pulls?{query}")
    if not isinstance(payload, list):
        raise GhError(f"Expected pull request list for {repo}.")
    merged: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        merged_at = str(item.get("merged_at") or "").strip()
        if not merged_at:
            continue
        try:
            number = int(item.get("number"))
        except (TypeError, ValueError):
            continue
        if since_pr is not None and number <= since_pr:
            continue
        if until_pr is not None and number > until_pr:
            continue
        merged.append(
            {
                "number": number,
                "merged_at": merged_at,
                "title": str(item.get("title") or ""),
            }
        )
    return sorted(merged, key=lambda item: (item["number"], item["merged_at"]))


def fetch_pr_files(root: Path, *, repo: str, pr_number: int) -> list[str]:
    query = urlencode({"per_page": 100})
    payload = _run_gh_json(root, "api", f"repos/{repo}/pulls/{pr_number}/files?{query}")
    if not isinstance(payload, list):
        raise GhError(f"Expected changed file list for PR #{pr_number} in {repo}.")
    files: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if filename:
            files.append(filename)
    return sorted(set(files))
