"""Git helpers for Ariadne v2."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

GITHUB_REMOTE_PATTERNS = (
    re.compile(r"^https://github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$"),
    re.compile(r"^git@github\.com:(?P<repo>[^/]+/[^/]+?)(?:\.git)?$"),
    re.compile(r"^ssh://git@github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$"),
)


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def is_git_repo(root: Path) -> bool:
    completed = _run(root, "rev-parse", "--is-inside-work-tree")
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def remote_url(root: Path, name: str = "origin") -> str | None:
    completed = _run(root, "remote", "get-url", name)
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def infer_github_repo(root: Path, remote_name: str = "origin") -> str | None:
    url = remote_url(root, remote_name)
    if not url:
        return None
    for pattern in GITHUB_REMOTE_PATTERNS:
        match = pattern.match(url)
        if match:
            return str(match.group("repo"))
    return None
