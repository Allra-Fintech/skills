#!/usr/bin/env python3
"""Ariadne v2 CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from ariadne_state import io
from ariadne_state.models import LEGACY_COMMANDS
from ariadne_state.runtime import check_runtime, init_runtime, removed_command_payload, report_runtime, resolve_runtime


def _common_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="Workspace root")


def _common_config_overrides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend-root", dest="backend_roots", action="append")
    parser.add_argument("--frontend-root", dest="frontend_roots", action="append")
    parser.add_argument("--backend-route-glob", dest="backend_route_globs", action="append")
    parser.add_argument("--frontend-glob", dest="frontend_globs", action="append")
    parser.add_argument("--ignore-glob", dest="ignore_globs", action="append")
    parser.add_argument("--full-rescan-glob", dest="full_rescan_globs", action="append")
    parser.add_argument("--path-normalization-rule", dest="path_normalization_rules", action="append")
    parser.add_argument("--frontend-wrapper-callee", dest="frontend_wrapper_callees", action="append")


def _common_remote_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", help="GitHub repo slug, for example owner/repo")
    parser.add_argument("--base-branch", help="GitHub base branch for merged PR tracking")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Ariadne v2 local state files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the Ariadne v2 catalog and initial state.")
    _common_root(init_parser)
    _common_config_overrides(init_parser)
    _common_remote_options(init_parser)

    check_parser = subparsers.add_parser("check", help="Refresh impacted APIs from merged GitHub PRs.")
    _common_root(check_parser)
    _common_config_overrides(check_parser)
    _common_remote_options(check_parser)
    check_parser.add_argument("--since-pr", type=int)
    check_parser.add_argument("--until-pr", type=int)
    check_parser.add_argument("--full-rescan", action="store_true")

    report_parser = subparsers.add_parser("report", help="Render the Ariadne v2 markdown report.")
    _common_root(report_parser)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve a needs-review record as matched or waived.")
    _common_root(resolve_parser)
    resolve_parser.add_argument("--api-key", required=True)
    resolve_parser.add_argument("--status", choices=("matched", "mismatch", "waived"), required=True)
    resolve_parser.add_argument("--reason-code")
    resolve_parser.add_argument("--note", required=True)

    for legacy_command in LEGACY_COMMANDS:
        legacy_parser = subparsers.add_parser(legacy_command, help=f"Removed in Ariadne v2: {legacy_command}")
        _common_root(legacy_parser)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "init":
        exit_code, payload = init_runtime(root, args)
        io.print_json(payload)
        return exit_code
    if args.command == "check":
        exit_code, payload = check_runtime(root, args)
        io.print_json(payload)
        return exit_code
    if args.command == "report":
        print(report_runtime(root), end="")
        return 0
    if args.command == "resolve":
        io.print_json(resolve_runtime(root, args))
        return 0
    if args.command in LEGACY_COMMANDS:
        io.print_json(removed_command_payload(args.command))
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
