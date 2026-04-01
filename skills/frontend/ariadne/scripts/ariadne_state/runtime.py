"""High-level runtime commands for Ariadne v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import io
from . import gh_tools
from .config import RuntimeConfig, apply_cli_overrides, load_config, render_config
from .evidence import collect_frontend_evidence
from .inventory import build_catalog
from .models import LEGACY_COMMANDS, empty_catalog, empty_state, empty_waivers
from .paths import ensure_state_layout, reset_for_v2
from .state import apply_resolution, candidate_api_keys, diff_records, evaluate_records, load_waivers, merge_incremental_records, render_waivers, summarize_records


def removed_command_payload(command: str) -> dict[str, Any]:
    return {
        "error": f"Command '{command}' was removed in Ariadne v2.",
        "hint": "Use init, check, report, or resolve.",
    }


def _load_state(path, *, repo: str | None = None, base_branch: str | None = None) -> dict[str, Any]:
    return io.load_json_or_default(
        path,
        empty_state(
            io.utc_now(),
            repo=repo,
            base_branch=base_branch,
            last_processed_pr_number=None,
            last_processed_merged_at=None,
        ),
    )


def _load_catalog(path) -> dict[str, Any]:
    return io.load_json_or_default(path, empty_catalog(io.utc_now()))


def _persist_bootstrap(layout, config: RuntimeConfig) -> None:
    io.atomic_write_text(layout.config_path, render_config(config))
    if not layout.waivers_path.exists():
        io.atomic_write_text(layout.waivers_path, render_waivers(empty_waivers()))


def _runtime_error(message: str) -> tuple[int, dict[str, Any]]:
    return 2, {
        "error": message,
        "hint": "Ariadne requires authenticated GitHub CLI access for remote PR tracking.",
    }


def _collect_pr_changed_files(root: Path, *, repo: str, prs: list[dict[str, Any]]) -> list[str]:
    changed: set[str] = set()
    for pr in prs:
        changed.update(gh_tools.fetch_pr_files(root, repo=repo, pr_number=int(pr["number"])))
    return sorted(changed)


def init_runtime(root: Path, args: Any) -> tuple[int, dict[str, Any]]:
    config = apply_cli_overrides(RuntimeConfig(), args)
    try:
        remote = gh_tools.resolve_remote_context(root, repo=args.repo, base_branch=args.base_branch)
        merged_prs = gh_tools.list_merged_prs(root, repo=remote["repo"], base_branch=remote["base_branch"], since_pr=None, until_pr=None)
    except gh_tools.GhError as exc:
        return _runtime_error(str(exc))

    layout = ensure_state_layout(root)
    reset_for_v2(layout)
    config = apply_cli_overrides(RuntimeConfig(), args)
    _persist_bootstrap(layout, config)

    timestamp = io.utc_now()
    catalog_payload = build_catalog(root, config)
    frontend_scan = collect_frontend_evidence(root, config)
    waivers_payload = load_waivers(layout.waivers_path)
    evaluated = evaluate_records(catalog_payload, frontend_scan, waivers_payload, {}, action="init", timestamp=timestamp)
    latest_pr = merged_prs[-1] if merged_prs else None
    state_payload = empty_state(
        timestamp,
        repo=remote["repo"],
        base_branch=remote["base_branch"],
        last_processed_pr_number=(int(latest_pr["number"]) if latest_pr else None),
        last_processed_merged_at=(str(latest_pr["merged_at"]) if latest_pr else None),
    )
    state_payload.update(
        {
            "last_init_at": timestamp,
            "updated_at": timestamp,
            "records": [evaluated[key] for key in sorted(evaluated)],
            "last_run": {
                "mode": "init",
                "repo": remote["repo"],
                "base_branch": remote["base_branch"],
                "since_pr": None,
                "until_pr": (int(latest_pr["number"]) if latest_pr else None),
                "processed_pr_count": 0,
                "processed_pr_numbers": [],
                "full_rescan": True,
                "changed_files": [],
                "changes": diff_records({}, evaluated),
            },
        }
    )

    io.atomic_write_json(layout.catalog_path, catalog_payload)
    io.atomic_write_json(layout.state_path, state_payload)
    return 0, {
        "state_dir": str(layout.state_dir),
        "catalog_api_count": catalog_payload["api_count"],
        "route_path_count": catalog_payload["route_path_count"],
        "record_count": len(state_payload["records"]),
        "remote": dict(state_payload["remote"]),
        "cursor": dict(state_payload["cursor"]),
        "summary": summarize_records(state_payload["records"]),
    }


def check_runtime(root: Path, args: Any) -> tuple[int, dict[str, Any]]:
    layout = ensure_state_layout(root)
    existing_config = load_config(layout.config_path)
    config = apply_cli_overrides(existing_config, args)
    previous_catalog = _load_catalog(layout.catalog_path)
    previous_state = _load_state(layout.state_path)
    previous_records = {str(record.get("api_key")): record for record in previous_state.get("records", []) if record.get("api_key")}
    previous_remote = dict(previous_state.get("remote") or {})
    previous_cursor = dict(previous_state.get("cursor") or {})
    try:
        remote = gh_tools.resolve_remote_context(
            root,
            repo=args.repo or previous_remote.get("repo"),
            base_branch=args.base_branch or previous_remote.get("base_branch"),
        )
        since_pr = args.since_pr if args.since_pr is not None else previous_cursor.get("last_processed_pr_number")
        until_pr = args.until_pr
        merged_prs = gh_tools.list_merged_prs(
            root,
            repo=remote["repo"],
            base_branch=remote["base_branch"],
            since_pr=(int(since_pr) if since_pr is not None else None),
            until_pr=(int(until_pr) if until_pr is not None else None),
        )
        changed_file_list = _collect_pr_changed_files(root, repo=remote["repo"], prs=merged_prs)
    except gh_tools.GhError as exc:
        return _runtime_error(str(exc))

    _persist_bootstrap(layout, config)

    timestamp = io.utc_now()
    waivers_payload = load_waivers(layout.waivers_path)
    current_catalog = build_catalog(root, config)
    frontend_scan = collect_frontend_evidence(root, config)
    evaluated = evaluate_records(current_catalog, frontend_scan, waivers_payload, previous_records, action="check", timestamp=timestamp)

    candidate_keys, full_rescan = candidate_api_keys(previous_catalog, current_catalog, previous_records, frontend_scan, changed_file_list, config)
    if args.full_rescan:
        full_rescan = True
        candidate_keys = set(evaluated)

    next_records_map = merge_incremental_records(previous_records, evaluated, candidate_keys, full_rescan=full_rescan)
    changes = diff_records(previous_records, next_records_map)
    next_cursor_number = previous_cursor.get("last_processed_pr_number")
    next_cursor_merged_at = previous_cursor.get("last_processed_merged_at")
    if merged_prs:
        next_cursor_number = int(merged_prs[-1]["number"])
        next_cursor_merged_at = str(merged_prs[-1]["merged_at"])

    next_state = dict(previous_state)
    next_state.update(
        {
            "updated_at": timestamp,
            "last_check_at": timestamp,
            "remote": {
                "repo": remote["repo"],
                "base_branch": remote["base_branch"],
            },
            "cursor": {
                "last_processed_pr_number": next_cursor_number,
                "last_processed_merged_at": next_cursor_merged_at,
            },
            "records": [next_records_map[key] for key in sorted(next_records_map)],
            "last_run": {
                "mode": "check",
                "repo": remote["repo"],
                "base_branch": remote["base_branch"],
                "since_pr": (int(since_pr) if since_pr is not None else None),
                "until_pr": (int(merged_prs[-1]["number"]) if merged_prs else (int(since_pr) if since_pr is not None else None)),
                "processed_pr_count": len(merged_prs),
                "processed_pr_numbers": [int(pr["number"]) for pr in merged_prs],
                "full_rescan": full_rescan,
                "changed_files": changed_file_list,
                "changes": changes,
            },
        }
    )

    io.atomic_write_text(layout.config_path, render_config(config))
    io.atomic_write_json(layout.catalog_path, current_catalog)
    io.atomic_write_json(layout.state_path, next_state)
    summary = summarize_records(next_state["records"])
    exit_code = 1 if summary["action_required_count"] else 0
    return exit_code, {
        "repo": remote["repo"],
        "base_branch": remote["base_branch"],
        "since_pr": (int(since_pr) if since_pr is not None else None),
        "until_pr": (int(merged_prs[-1]["number"]) if merged_prs else (int(since_pr) if since_pr is not None else None)),
        "processed_pr_count": len(merged_prs),
        "processed_pr_numbers": [int(pr["number"]) for pr in merged_prs],
        "full_rescan": full_rescan,
        "changed_files": changed_file_list,
        "candidate_api_keys": sorted(candidate_keys),
        "changed_api_count": len(changes),
        "summary": summary,
    }


def resolve_runtime(root: Path, args: Any) -> dict[str, Any]:
    layout = ensure_state_layout(root)
    state_payload = _load_state(layout.state_path)
    waivers_payload = load_waivers(layout.waivers_path)
    timestamp = io.utc_now()
    if args.status == "waived":
        reason_code = args.reason_code or "manual-waiver"
    elif args.status == "mismatch":
        reason_code = args.reason_code or "manual-mismatch"
    else:
        reason_code = args.reason_code or "manual-match"
    next_state, next_waivers, record = apply_resolution(
        state_payload,
        waivers_payload,
        api_key=args.api_key,
        status=args.status,
        reason_code=reason_code,
        note=args.note or "",
        timestamp=timestamp,
    )
    io.atomic_write_json(layout.state_path, next_state)
    io.atomic_write_text(layout.waivers_path, render_waivers(next_waivers))
    return {
        "api_key": args.api_key,
        "status": record["status"],
        "reason_code": record["reason_code"],
    }


def report_runtime(root: Path) -> str:
    from .report import render_markdown

    layout = ensure_state_layout(root)
    state_payload = _load_state(layout.state_path)
    waivers_payload = load_waivers(layout.waivers_path)
    return render_markdown(state_payload, waivers_payload)
