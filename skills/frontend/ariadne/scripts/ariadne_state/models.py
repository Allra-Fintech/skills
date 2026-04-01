"""Data defaults and constants for Ariadne v2."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

TOOL_NAME = "ariadne"
SCHEMA_VERSION = 2
STATUSES = ("matched", "missing", "mismatch", "needs-review", "waived")
LEGACY_COMMANDS = (
    "finalize-check",
    "write-backend-summary",
    "write-api-catalog",
    "write-impact-index",
    "upsert-record",
    "upsert-pr-ledger",
    "list-recheck-targets",
    "rebuild-summary",
    "refresh-rubric",
    "record-run",
)


def clone(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)


def empty_catalog(timestamp: str) -> dict[str, Any]:
    return {
        "tool": TOOL_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at": timestamp,
        "api_count": 0,
        "route_path_count": 0,
        "records": [],
        "backend_file_index": {},
    }


def empty_state(
    timestamp: str,
    *,
    repo: str | None,
    base_branch: str | None,
    last_processed_pr_number: int | None,
    last_processed_merged_at: str | None,
) -> dict[str, Any]:
    return {
        "tool": TOOL_NAME,
        "schema_version": SCHEMA_VERSION,
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_init_at": None,
        "last_check_at": None,
        "remote": {
            "repo": repo,
            "base_branch": base_branch,
        },
        "cursor": {
            "last_processed_pr_number": last_processed_pr_number,
            "last_processed_merged_at": last_processed_merged_at,
        },
        "records": [],
        "last_run": {},
    }


def default_record(api_key: str, method: str, normalized_path: str) -> dict[str, Any]:
    return {
        "api_key": api_key,
        "method": method,
        "normalized_path": normalized_path,
        "status": "needs-review",
        "reason_code": "uncertain-binding",
        "backend_evidence": [],
        "frontend_evidence": [],
        "audit": [],
        "manual_resolution": None,
        "last_checked_at": None,
        "last_updated_at": None,
    }


def empty_waivers() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "waivers": [],
    }
