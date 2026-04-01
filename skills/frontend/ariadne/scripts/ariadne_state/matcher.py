"""Glob and root matching helpers for Ariadne v2."""

from __future__ import annotations

import fnmatch
from functools import lru_cache
from typing import Iterable


def normalize_glob_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _split_segments(value: str) -> tuple[str, ...]:
    normalized = normalize_glob_path(value)
    if not normalized:
        return ()
    return tuple(segment for segment in normalized.split("/") if segment and segment != ".")


def path_matches_pattern(path: str, pattern: str) -> bool:
    path_segments = _split_segments(path)
    pattern_segments = _split_segments(pattern)
    if not pattern_segments:
        return not path_segments

    @lru_cache(maxsize=None)
    def matches(path_index: int, pattern_index: int) -> bool:
        if pattern_index >= len(pattern_segments):
            return path_index >= len(path_segments)
        segment = pattern_segments[pattern_index]
        if segment == "**":
            return matches(path_index, pattern_index + 1) or (
                path_index < len(path_segments) and matches(path_index + 1, pattern_index)
            )
        if path_index >= len(path_segments):
            return False
        if not fnmatch.fnmatchcase(path_segments[path_index], segment):
            return False
        return matches(path_index + 1, pattern_index + 1)

    return matches(0, 0)


def path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(pattern and path_matches_pattern(path, pattern) for pattern in patterns)


def under_any_root(path: str, roots: Iterable[str]) -> bool:
    normalized_path = normalize_glob_path(path)
    normalized_roots = [normalize_glob_path(root) for root in roots if normalize_glob_path(root)]
    if not normalized_roots:
        return True
    return any(normalized_path == root or normalized_path.startswith(root.rstrip("/") + "/") for root in normalized_roots)
