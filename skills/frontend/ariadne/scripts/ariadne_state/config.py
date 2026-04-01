"""Config loading and rendering for Ariadne v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import io


@dataclass
class RuntimeConfig:
    backend_roots: list[str] = field(default_factory=lambda: ["backend"])
    frontend_roots: list[str] = field(default_factory=lambda: ["src"])
    backend_route_globs: list[str] = field(
        default_factory=lambda: [
            "**/*controller.ts",
            "**/*controller.js",
            "**/*route.ts",
            "**/*route.js",
            "**/*router.ts",
            "**/*router.js",
            "**/*.py",
            "**/*Controller.java",
        ]
    )
    frontend_globs: list[str] = field(
        default_factory=lambda: [
            "src/**/*.ts",
            "src/**/*.tsx",
            "src/**/*.js",
            "src/**/*.jsx",
            "src/**/*.py",
            "app/**/*.ts",
            "app/**/*.tsx",
            "app/**/*.js",
            "app/**/*.jsx",
        ]
    )
    ignore_globs: list[str] = field(
        default_factory=lambda: [
            "**/*.test.ts",
            "**/*.spec.ts",
            "**/__tests__/**",
            "**/node_modules/**",
        ]
    )
    full_rescan_globs: list[str] = field(default_factory=lambda: ["src/lib/http/**/*.ts", "src/shared/http/**/*.ts"])
    path_normalization_rules: list[dict[str, str]] = field(default_factory=list)
    frontend_wrapper_callees: list[str] = field(default_factory=list)


def _list_value(payload: dict[str, Any], key: str, default: list[str]) -> list[str]:
    value = payload.get(key, default)
    if not isinstance(value, list):
        return list(default)
    return [str(item).strip() for item in value if str(item).strip()]


def _rule_value(payload: dict[str, Any], key: str) -> list[dict[str, str]]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        return []
    rules: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        match = str(item.get("match") or "").strip()
        if not match:
            continue
        rules.append({"match": match, "replace": str(item.get("replace") or "")})
    return rules


def load_config(path: Path) -> RuntimeConfig:
    if not path.exists():
        return RuntimeConfig()
    payload = io.load_simple_yaml(path)
    config = RuntimeConfig()
    config.backend_roots = _list_value(payload, "backend_roots", config.backend_roots)
    config.frontend_roots = _list_value(payload, "frontend_roots", config.frontend_roots)
    config.backend_route_globs = _list_value(payload, "backend_route_globs", config.backend_route_globs)
    config.frontend_globs = _list_value(payload, "frontend_globs", config.frontend_globs)
    config.ignore_globs = _list_value(payload, "ignore_globs", config.ignore_globs)
    config.full_rescan_globs = _list_value(payload, "full_rescan_globs", config.full_rescan_globs)
    config.path_normalization_rules = _rule_value(payload, "path_normalization_rules")
    config.frontend_wrapper_callees = _list_value(payload, "frontend_wrapper_callees", config.frontend_wrapper_callees)
    return config


def apply_cli_overrides(config: RuntimeConfig, args: Any) -> RuntimeConfig:
    if getattr(args, "backend_roots", None):
        config.backend_roots = list(args.backend_roots)
    if getattr(args, "frontend_roots", None):
        config.frontend_roots = list(args.frontend_roots)
    if getattr(args, "backend_route_globs", None):
        config.backend_route_globs = list(args.backend_route_globs)
    if getattr(args, "frontend_globs", None):
        config.frontend_globs = list(args.frontend_globs)
    if getattr(args, "ignore_globs", None):
        config.ignore_globs = list(args.ignore_globs)
    if getattr(args, "full_rescan_globs", None):
        config.full_rescan_globs = list(args.full_rescan_globs)
    if getattr(args, "frontend_wrapper_callees", None):
        config.frontend_wrapper_callees = list(args.frontend_wrapper_callees)
    if getattr(args, "path_normalization_rules", None):
        rules: list[dict[str, str]] = []
        for raw_rule in args.path_normalization_rules:
            match, _, replace = raw_rule.partition("=")
            if match.strip():
                rules.append({"match": match.strip(), "replace": replace})
        if rules:
            config.path_normalization_rules = rules
    return config


def render_config(config: RuntimeConfig) -> str:
    return "\n".join(
        [
            "schema_version: 2",
            "",
            io.yaml_keyed_list("backend_roots", config.backend_roots),
            "",
            io.yaml_keyed_list("frontend_roots", config.frontend_roots),
            "",
            io.yaml_keyed_list("backend_route_globs", config.backend_route_globs),
            "",
            io.yaml_keyed_list("frontend_globs", config.frontend_globs),
            "",
            io.yaml_keyed_list("ignore_globs", config.ignore_globs),
            "",
            io.yaml_keyed_list("full_rescan_globs", config.full_rescan_globs),
            "",
            io.yaml_keyed_rule_list("path_normalization_rules", config.path_normalization_rules),
            "",
            io.yaml_keyed_list("frontend_wrapper_callees", config.frontend_wrapper_callees),
            "",
        ]
    )
