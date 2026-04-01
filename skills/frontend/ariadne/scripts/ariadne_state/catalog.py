"""Catalog and path helpers for Ariadne v2."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

PATH_PARAM_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)|<([A-Za-z_][A-Za-z0-9_:]*)>|{([A-Za-z_][A-Za-z0-9_]*)}")
PATH_SHAPE_RE = re.compile(r"{[^/{}]+}")
TEMPLATE_PARAM_RE = re.compile(r"\$\{[^}]+\}")


def build_api_key(method: str, normalized_path: str) -> str:
    method_name = method.strip().upper()
    path = normalize_path(normalized_path)
    return f"{method_name} {path}"


def normalize_path(raw_path: str, rules: list[dict[str, str]] | None = None) -> str:
    normalized = raw_path.strip() if raw_path else "/"
    normalized = TEMPLATE_PARAM_RE.sub("{param}", normalized)
    if not normalized.startswith("/"):
        normalized = "/" + normalized.lstrip("/")
    normalized = re.sub(r"/{2,}", "/", normalized)

    def replace_param(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2) or match.group(3) or "param"
        return f"{{{name.split(':')[-1]}}}"

    normalized = PATH_PARAM_RE.sub(replace_param, normalized)
    for rule in rules or []:
        match = str(rule.get("match") or "").strip()
        if not match:
            continue
        normalized = re.sub(match, str(rule.get("replace") or ""), normalized)
    normalized = re.sub(r"/{2,}", "/", normalized)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized or "/"


def path_shape(path: str) -> str:
    return PATH_SHAPE_RE.sub("{}", normalize_path(path))


def stable_signature_hash(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()
