"""Frontend evidence collection for Ariadne v2."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import catalog, matcher
from .config import RuntimeConfig

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")
LINE_BREAK_RE = re.compile(r"\r\n|\r|\n")
QUOTE_PATH_RE = r"(?P<quote>`|'|\")(?P<path>[^`'\"]+)(?P=quote)"
FETCH_RE = re.compile(rf"\bfetch\(\s*{QUOTE_PATH_RE}(?P<tail>[^)]*)\)", re.IGNORECASE)
METHOD_CALL_RE = re.compile(
    rf"\b(?P<client>axios|requests|httpx|client|api|http)\.(?P<method>get|post|put|patch|delete|options|head)\(\s*{QUOTE_PATH_RE}",
    re.IGNORECASE,
)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def discover_paths(root: Path, *, roots: list[str], include_globs: list[str], ignore_globs: list[str]) -> list[str]:
    discovered: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if roots and not matcher.under_any_root(relative, roots):
            continue
        if include_globs and not matcher.path_matches_any(relative, include_globs):
            continue
        if ignore_globs and matcher.path_matches_any(relative, ignore_globs):
            continue
        discovered.append(relative)
    return sorted(set(discovered))


def _exact_evidence(file_path: str, line: int, extractor: str, method: str, normalized_path: str) -> dict[str, Any]:
    api_key = catalog.build_api_key(method, normalized_path)
    return {
        "api_key": api_key,
        "file": file_path,
        "line": line,
        "extractor": extractor,
        "method": method,
        "normalized_path": normalized_path,
        "path_shape": catalog.path_shape(normalized_path),
        "confidence": "exact",
    }


def _shape_evidence(file_path: str, line: int, extractor: str, method: str | None, raw_path: str) -> dict[str, Any]:
    normalized_path = catalog.normalize_path(raw_path)
    return {
        "api_key": None,
        "file": file_path,
        "line": line,
        "extractor": extractor,
        "method": method,
        "normalized_path": normalized_path,
        "path_shape": catalog.path_shape(normalized_path),
        "confidence": "needs-review",
    }


def _extract_fetch_calls(text: str, file_path: str, rules: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    for match in FETCH_RE.finditer(text):
        raw_path = match.group("path")
        quote = match.group("quote")
        tail = match.group("tail") or ""
        method_match = re.search(r"method\s*:\s*['\"](GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)['\"]", tail, re.IGNORECASE)
        method = (method_match.group(1).upper() if method_match else "GET")
        line = _line_number(text, match.start())
        if quote == "`" and "${" in raw_path:
            uncertain.append(_shape_evidence(file_path, line, "fetch-template", method, raw_path))
            continue
        exact.append(_exact_evidence(file_path, line, "fetch", method, catalog.normalize_path(raw_path, rules)))
    return exact, uncertain


def _extract_method_calls(text: str, file_path: str, rules: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    for match in METHOD_CALL_RE.finditer(text):
        raw_path = match.group("path")
        quote = match.group("quote")
        method = match.group("method").upper()
        line = _line_number(text, match.start())
        if quote == "`" and "${" in raw_path:
            uncertain.append(_shape_evidence(file_path, line, f"{match.group('client')}-template", method, raw_path))
            continue
        exact.append(_exact_evidence(file_path, line, match.group("client").lower(), method, catalog.normalize_path(raw_path, rules)))
    return exact, uncertain


def _extract_wrapper_calls(
    text: str,
    file_path: str,
    rules: list[dict[str, str]],
    wrapper_callees: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    for callee in wrapper_callees:
        pattern = re.compile(rf"\b{re.escape(callee)}\(\s*\{{(?P<body>.*?)\}}\s*\)", re.DOTALL)
        for match in pattern.finditer(text):
            body = match.group("body")
            line = _line_number(text, match.start())
            method_match = re.search(r"method\s*:\s*['\"](GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)['\"]", body, re.IGNORECASE)
            path_match = re.search(r"(?:path|url|pattern)\s*:\s*(`[^`]+`|'[^']+'|\"[^\"]+\")", body, re.IGNORECASE)
            method = method_match.group(1).upper() if method_match else None
            if not path_match:
                uncertain.append(_shape_evidence(file_path, line, f"{callee}-hint", method, "/unknown"))
                continue
            raw_value = path_match.group(1)[1:-1]
            if path_match.group(1).startswith("`") and "${" in raw_value:
                uncertain.append(_shape_evidence(file_path, line, f"{callee}-template", method, raw_value))
                continue
            if method is None:
                uncertain.append(_shape_evidence(file_path, line, f"{callee}-missing-method", None, raw_value))
                continue
            exact.append(_exact_evidence(file_path, line, f"{callee}-hint", method, catalog.normalize_path(raw_value, rules)))
    return exact, uncertain


def collect_frontend_evidence(root: Path, config: RuntimeConfig) -> dict[str, Any]:
    exact_evidence: list[dict[str, Any]] = []
    uncertain_evidence: list[dict[str, Any]] = []
    file_index: dict[str, set[str]] = {}
    shape_file_index: dict[str, set[str]] = {}

    frontend_paths = discover_paths(
        root,
        roots=config.frontend_roots,
        include_globs=config.frontend_globs,
        ignore_globs=config.ignore_globs,
    )

    for file_path in frontend_paths:
        text = (root / file_path).read_text(encoding="utf-8")
        groups = [
            _extract_fetch_calls(text, file_path, config.path_normalization_rules),
            _extract_method_calls(text, file_path, config.path_normalization_rules),
            _extract_wrapper_calls(text, file_path, config.path_normalization_rules, config.frontend_wrapper_callees),
        ]
        for exact_group, uncertain_group in groups:
            exact_evidence.extend(exact_group)
            uncertain_evidence.extend(uncertain_group)

    exact_by_api_key: dict[str, list[dict[str, Any]]] = {}
    exact_by_path: dict[str, list[dict[str, Any]]] = {}
    shape_hits: dict[str, list[dict[str, Any]]] = {}
    for item in exact_evidence:
        api_key = str(item["api_key"])
        exact_by_api_key.setdefault(api_key, []).append(item)
        exact_by_path.setdefault(str(item["normalized_path"]), []).append(item)
        file_index.setdefault(str(item["file"]), set()).add(api_key)
    for item in uncertain_evidence:
        shape = str(item.get("path_shape") or "")
        if not shape:
            continue
        shape_hits.setdefault(shape, []).append(item)
        shape_file_index.setdefault(str(item["file"]), set()).add(shape)

    return {
        "frontend_paths": frontend_paths,
        "exact_by_api_key": {key: sorted(value, key=lambda item: (item["file"], item["line"])) for key, value in sorted(exact_by_api_key.items())},
        "exact_by_path": {key: sorted(value, key=lambda item: (item["file"], item["line"])) for key, value in sorted(exact_by_path.items())},
        "shape_hits": {key: sorted(value, key=lambda item: (item["file"], item["line"])) for key, value in sorted(shape_hits.items())},
        "file_index": {key: sorted(values) for key, values in sorted(file_index.items())},
        "shape_file_index": {key: sorted(values) for key, values in sorted(shape_file_index.items())},
        "exact_count": len(exact_evidence),
        "uncertain_count": len(uncertain_evidence),
    }
