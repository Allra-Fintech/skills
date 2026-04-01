"""Backend inventory extraction for Ariadne v2."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import catalog, io, matcher
from .config import RuntimeConfig
from .evidence import discover_paths
from .models import SCHEMA_VERSION, TOOL_NAME

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _join_paths(prefix: str, raw_path: str) -> str:
    joined = f"{prefix.rstrip('/')}/{raw_path.lstrip('/')}" if prefix else raw_path
    return catalog.normalize_path(joined)


def _extract_js_chain(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"\b(?:router|app|fastify)\.(get|post|put|patch|delete|options|head)\(\s*(['\"])([^'\"\n`]+)\2",
        re.IGNORECASE,
    )
    matches: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        matches.append(
            {
                "method": match.group(1).upper(),
                "raw_path": match.group(3),
                "line": _line_number(text, match.start()),
                "extractor": "route-chain",
            }
        )
    return matches


def _extract_js_decorators(text: str) -> list[dict[str, Any]]:
    controller_prefix_match = re.search(r"@Controller\(\s*(['\"])([^'\"]*)\1\s*\)", text)
    controller_prefix = controller_prefix_match.group(2) if controller_prefix_match else ""
    pattern = re.compile(r"@(Get|Post|Put|Patch|Delete|Options|Head)\(\s*(['\"]?)([^)'\"]*)\2\s*\)")
    matches: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        matches.append(
            {
                "method": match.group(1).upper(),
                "raw_path": _join_paths(controller_prefix, match.group(3) or "/"),
                "line": _line_number(text, match.start()),
                "extractor": "decorator-route",
            }
        )
    return matches


def _extract_python_routes(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"@(app|router|bp|blueprint)\.(get|post|put|patch|delete|options|head)\(\s*(['\"])([^'\"]+)\3",
        re.IGNORECASE,
    )
    matches: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        matches.append(
            {
                "method": match.group(2).upper(),
                "raw_path": match.group(4),
                "line": _line_number(text, match.start()),
                "extractor": "python-decorator",
            }
        )
    route_pattern = re.compile(r"@(?:app|router)\.route\(\s*(['\"])([^'\"]+)\1\s*,\s*methods\s*=\s*\[(.*?)\]", re.IGNORECASE | re.DOTALL)
    for match in route_pattern.finditer(text):
        methods = re.findall(r"['\"](GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)['\"]", match.group(3), re.IGNORECASE)
        for method in methods:
            matches.append(
                {
                    "method": method.upper(),
                    "raw_path": match.group(2),
                    "line": _line_number(text, match.start()),
                    "extractor": "python-route",
                }
            )
    return matches


def _extract_java_routes(text: str) -> list[dict[str, Any]]:
    class_match = re.search(r"@RequestMapping\(\s*(['\"])([^'\"]*)\1\s*\)", text)
    class_prefix = class_match.group(2) if class_match else ""
    basic_pattern = re.compile(r"@(Get|Post|Put|Patch|Delete|Options|Head)Mapping\(\s*(['\"]?)([^)'\"]*)\2\s*\)")
    matches: list[dict[str, Any]] = []
    for match in basic_pattern.finditer(text):
        matches.append(
            {
                "method": match.group(1).upper(),
                "raw_path": _join_paths(class_prefix, match.group(3) or "/"),
                "line": _line_number(text, match.start()),
                "extractor": "java-mapping",
            }
        )
    request_mapping = re.compile(r"@RequestMapping\((?P<body>.*?)\)", re.DOTALL)
    for match in request_mapping.finditer(text):
        body = match.group("body")
        method_match = re.search(r"RequestMethod\.(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)", body)
        path_match = re.search(r"(?:path|value)\s*=\s*['\"]([^'\"]+)['\"]", body)
        if not method_match or not path_match:
            continue
        matches.append(
            {
                "method": method_match.group(1).upper(),
                "raw_path": _join_paths(class_prefix, path_match.group(1)),
                "line": _line_number(text, match.start()),
                "extractor": "java-request-mapping",
            }
        )
    return matches


def build_catalog(root: Path, config: RuntimeConfig) -> dict[str, Any]:
    route_paths = discover_paths(
        root,
        roots=config.backend_roots,
        include_globs=config.backend_route_globs,
        ignore_globs=config.ignore_globs,
    )
    record_index: dict[str, dict[str, Any]] = {}
    backend_file_index: dict[str, set[str]] = {}

    for file_path in route_paths:
        text = (root / file_path).read_text(encoding="utf-8")
        extracted: list[dict[str, Any]] = []
        lowered = file_path.lower()
        if lowered.endswith((".ts", ".js")):
            extracted.extend(_extract_js_chain(text))
            extracted.extend(_extract_js_decorators(text))
        elif lowered.endswith(".py"):
            extracted.extend(_extract_python_routes(text))
        elif lowered.endswith(".java"):
            extracted.extend(_extract_java_routes(text))
        for item in extracted:
            normalized_path = catalog.normalize_path(item["raw_path"], config.path_normalization_rules)
            api_key = catalog.build_api_key(item["method"], normalized_path)
            record = record_index.setdefault(
                api_key,
                {
                    "api_key": api_key,
                    "method": item["method"],
                    "normalized_path": normalized_path,
                    "raw_paths": [],
                    "route_files": [],
                    "backend_evidence": [],
                    "catalog_signature_hash": "",
                },
            )
            record["raw_paths"] = sorted(set(record["raw_paths"] + [item["raw_path"]]))
            record["route_files"] = sorted(set(record["route_files"] + [file_path]))
            record["backend_evidence"].append(
                {
                    "file": file_path,
                    "line": item["line"],
                    "extractor": item["extractor"],
                    "method": item["method"],
                    "raw_path": item["raw_path"],
                }
            )
            backend_file_index.setdefault(file_path, set()).add(api_key)

    records = [record_index[key] for key in sorted(record_index)]
    for record in records:
        record["backend_evidence"] = sorted(record["backend_evidence"], key=lambda item: (item["file"], item["line"]))
        record["catalog_signature_hash"] = catalog.stable_signature_hash(
            {
                "api_key": record["api_key"],
                "route_files": record["route_files"],
                "raw_paths": record["raw_paths"],
            }
        )

    return {
        "tool": TOOL_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at": io.utc_now(),
        "api_count": len(records),
        "route_path_count": len(route_paths),
        "records": records,
        "backend_file_index": {path: sorted(values) for path, values in sorted(backend_file_index.items())},
    }
