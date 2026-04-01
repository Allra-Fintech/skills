"""State evaluation and resolution helpers for Ariadne v2."""

from __future__ import annotations

from typing import Any

from . import catalog, io, matcher
from .config import RuntimeConfig
from .models import STATUSES, default_record


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in STATUSES}
    for record in records:
        status = str(record.get("status") or "")
        if status in counts:
            counts[status] += 1
    return {
        "record_count": len(records),
        "status_counts": counts,
        "action_required_count": counts["missing"] + counts["mismatch"] + counts["needs-review"],
    }


def load_waivers(path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 2, "waivers": []}
    payload = io.load_simple_yaml(path)
    waivers = payload.get("waivers", [])
    if not isinstance(waivers, list):
        waivers = []
    normalized: list[dict[str, Any]] = []
    for item in waivers:
        if not isinstance(item, dict):
            continue
        api_key = str(item.get("api_key") or "").strip()
        if not api_key:
            continue
        normalized.append(
            {
                "api_key": api_key,
                "reason_code": str(item.get("reason_code") or "manual-waiver"),
                "note": str(item.get("note") or ""),
                "updated_at": str(item.get("updated_at") or ""),
            }
        )
    return {"schema_version": 2, "waivers": normalized}


def render_waivers(payload: dict[str, Any]) -> str:
    lines = ["schema_version: 2", "", "waivers:"]
    waivers = list(payload.get("waivers") or [])
    if not waivers:
        lines.append("  []")
        return "\n".join(lines) + "\n"
    for item in waivers:
        lines.append(f'  - api_key: {io.yaml_quote(str(item.get("api_key") or ""))}')
        lines.append(f'    reason_code: {io.yaml_quote(str(item.get("reason_code") or "manual-waiver"))}')
        lines.append(f'    note: {io.yaml_quote(str(item.get("note") or ""))}')
        lines.append(f'    updated_at: {io.yaml_quote(str(item.get("updated_at") or ""))}')
    lines.append("")
    return "\n".join(lines)


def _waiver_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("api_key")): item for item in payload.get("waivers", []) if item.get("api_key")}


def _append_audit(previous: dict[str, Any], current: dict[str, Any], *, action: str, timestamp: str, note: str | None = None) -> list[dict[str, Any]]:
    audit = list(previous.get("audit") or [])
    if previous.get("status") == current.get("status") and previous.get("reason_code") == current.get("reason_code") and note is None:
        return audit
    audit.append(
        {
            "at": timestamp,
            "action": action,
            "from_status": previous.get("status"),
            "to_status": current.get("status"),
            "reason_code": current.get("reason_code"),
            "note": note,
        }
    )
    return audit


def _record_from_catalog(record: dict[str, Any], status: str, reason_code: str, frontend_evidence: list[dict[str, Any]], timestamp: str) -> dict[str, Any]:
    payload = default_record(record["api_key"], record["method"], record["normalized_path"])
    payload.update(
        {
            "status": status,
            "reason_code": reason_code,
            "backend_evidence": list(record.get("backend_evidence") or []),
            "frontend_evidence": frontend_evidence,
            "last_checked_at": timestamp,
            "last_updated_at": timestamp,
        }
    )
    return payload


def _conflicts_with_manual_resolution(previous: dict[str, Any], candidate: dict[str, Any], *, api_present: bool) -> bool:
    manual = previous.get("manual_resolution")
    if not isinstance(manual, dict):
        return False
    if not api_present and list(previous.get("backend_evidence") or []):
        return True
    manual_status = str(manual.get("status") or "")
    candidate_status = str(candidate.get("status") or "")
    candidate_reason = str(candidate.get("reason_code") or "")
    if manual_status == "matched" and candidate_reason in ("method-path-drift", "frontend-only"):
        return True
    if manual_status == "mismatch" and candidate_status == "matched":
        return True
    return False


def _apply_manual_resolution(previous: dict[str, Any], candidate: dict[str, Any], *, api_present: bool) -> dict[str, Any]:
    manual = previous.get("manual_resolution")
    if not isinstance(manual, dict):
        return candidate
    output = dict(candidate)
    output["manual_resolution"] = dict(manual)
    if _conflicts_with_manual_resolution(previous, candidate, api_present=api_present):
        output["status"] = "needs-review"
        output["reason_code"] = "manual-resolution-conflict"
        return output
    output["status"] = str(manual.get("status") or output.get("status") or "needs-review")
    output["reason_code"] = str(manual.get("reason_code") or output.get("reason_code") or "manual-resolution")
    return output


def evaluate_records(
    catalog_payload: dict[str, Any],
    frontend_scan: dict[str, Any],
    waivers_payload: dict[str, Any],
    previous_records: dict[str, dict[str, Any]],
    *,
    action: str,
    timestamp: str,
) -> dict[str, dict[str, Any]]:
    evaluated: dict[str, dict[str, Any]] = {}
    waiver_lookup = _waiver_lookup(waivers_payload)
    catalog_records = list(catalog_payload.get("records") or [])
    known_api_keys = {str(record.get("api_key")) for record in catalog_records}

    for record in catalog_records:
        api_key = str(record["api_key"])
        previous = previous_records.get(api_key, {})
        exact_hits = list(frontend_scan.get("exact_by_api_key", {}).get(api_key, []))
        path_hits = [
            item
            for item in frontend_scan.get("exact_by_path", {}).get(str(record["normalized_path"]), [])
            if str(item.get("api_key")) != api_key
        ]
        shape_hits = list(frontend_scan.get("shape_hits", {}).get(catalog.path_shape(str(record["normalized_path"])), []))

        if api_key in waiver_lookup:
            next_record = _record_from_catalog(record, "waived", str(waiver_lookup[api_key]["reason_code"] or "manual-waiver"), exact_hits or path_hits or shape_hits, timestamp)
        elif exact_hits:
            next_record = _record_from_catalog(record, "matched", str(exact_hits[0].get("extractor") or "direct-evidence"), exact_hits, timestamp)
        elif path_hits:
            next_record = _record_from_catalog(record, "needs-review", "method-path-drift", path_hits, timestamp)
        elif shape_hits:
            next_record = _record_from_catalog(record, "needs-review", "uncertain-binding", shape_hits, timestamp)
        else:
            next_record = _record_from_catalog(record, "missing", "no-frontend-evidence", [], timestamp)

        next_record = _apply_manual_resolution(previous, next_record, api_present=True)
        next_record["audit"] = _append_audit(previous, next_record, action=action, timestamp=timestamp)
        evaluated[api_key] = next_record

    for api_key, hits in frontend_scan.get("exact_by_api_key", {}).items():
        if api_key in known_api_keys:
            continue
        previous = previous_records.get(api_key, {})
        normalized_path = str(hits[0].get("normalized_path") or "/")
        method = str(hits[0].get("method") or "GET")
        next_record = default_record(api_key, method, normalized_path)
        next_record.update(
            {
                "status": "needs-review",
                "reason_code": "frontend-only",
                "frontend_evidence": hits,
                "last_checked_at": timestamp,
                "last_updated_at": timestamp,
            }
        )
        if api_key in waiver_lookup:
            next_record["status"] = "waived"
            next_record["reason_code"] = str(waiver_lookup[api_key]["reason_code"] or "manual-waiver")
        next_record = _apply_manual_resolution(previous, next_record, api_present=False)
        next_record["audit"] = _append_audit(previous, next_record, action=action, timestamp=timestamp)
        evaluated[api_key] = next_record

    for api_key, previous in previous_records.items():
        if api_key in evaluated or api_key in known_api_keys:
            continue
        manual = previous.get("manual_resolution")
        if not isinstance(manual, dict):
            continue
        next_record = default_record(
            str(previous.get("api_key") or api_key),
            str(previous.get("method") or "GET"),
            str(previous.get("normalized_path") or "/"),
        )
        next_record.update(
            {
                "status": "needs-review",
                "reason_code": "manual-resolution-conflict",
                "backend_evidence": list(previous.get("backend_evidence") or []),
                "frontend_evidence": list(previous.get("frontend_evidence") or []),
                "manual_resolution": dict(manual),
                "last_checked_at": timestamp,
                "last_updated_at": timestamp,
            }
        )
        next_record["audit"] = _append_audit(previous, next_record, action=action, timestamp=timestamp)
        evaluated[api_key] = next_record

    return evaluated


def candidate_api_keys(
    previous_catalog: dict[str, Any],
    current_catalog: dict[str, Any],
    previous_records: dict[str, dict[str, Any]],
    frontend_scan: dict[str, Any],
    changed_files: list[str],
    config: RuntimeConfig,
) -> tuple[set[str], bool]:
    candidates: set[str] = set()
    full_rescan = False
    current_shape_index: dict[str, set[str]] = {}
    for record in current_catalog.get("records", []):
        current_shape_index.setdefault(catalog.path_shape(str(record["normalized_path"])), set()).add(str(record["api_key"]))

    previous_backend_index = previous_catalog.get("backend_file_index", {})
    current_backend_index = current_catalog.get("backend_file_index", {})
    previous_frontend_index: dict[str, set[str]] = {}
    for api_key, record in previous_records.items():
        for item in record.get("frontend_evidence", []):
            file_path = str(item.get("file") or "")
            if file_path:
                previous_frontend_index.setdefault(file_path, set()).add(api_key)

    for file_path in changed_files:
        if matcher.path_matches_any(file_path, config.full_rescan_globs):
            full_rescan = True
        candidates.update(previous_backend_index.get(file_path, []))
        candidates.update(current_backend_index.get(file_path, []))
        candidates.update(previous_frontend_index.get(file_path, set()))
        candidates.update(frontend_scan.get("file_index", {}).get(file_path, []))
        for shape in frontend_scan.get("shape_file_index", {}).get(file_path, []):
            candidates.update(current_shape_index.get(shape, set()))

    return candidates, full_rescan


def merge_incremental_records(
    previous_records: dict[str, dict[str, Any]],
    evaluated_records: dict[str, dict[str, Any]],
    candidate_keys: set[str],
    *,
    full_rescan: bool,
) -> dict[str, dict[str, Any]]:
    if full_rescan:
        return evaluated_records
    merged = {key: dict(value) for key, value in previous_records.items()}
    for api_key in candidate_keys:
        if api_key in evaluated_records:
            merged[api_key] = evaluated_records[api_key]
        else:
            merged.pop(api_key, None)
    return merged


def diff_records(previous_records: dict[str, dict[str, Any]], next_records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted(set(previous_records) | set(next_records))
    changes: list[dict[str, Any]] = []
    for api_key in keys:
        previous = previous_records.get(api_key)
        current = next_records.get(api_key)
        if previous == current:
            continue
        previous_status = previous.get("status") if previous else None
        current_status = current.get("status") if current else "removed"
        previous_reason = previous.get("reason_code") if previous else None
        current_reason = current.get("reason_code") if current else "removed-from-tracking"
        if previous_status == current_status and previous_reason == current_reason:
            continue
        changes.append(
            {
                "api_key": api_key,
                "previous_status": previous_status,
                "status": current_status,
                "reason_code": current_reason,
            }
        )
    return changes


def apply_resolution(
    state_payload: dict[str, Any],
    waivers_payload: dict[str, Any],
    *,
    api_key: str,
    status: str,
    reason_code: str,
    note: str,
    timestamp: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    records = {str(record.get("api_key")): dict(record) for record in state_payload.get("records", []) if record.get("api_key")}
    if api_key not in records:
        raise ValueError(f"Unknown api_key: {api_key}")
    record = records[api_key]
    previous = dict(record)
    record["status"] = status
    record["reason_code"] = reason_code
    record["manual_resolution"] = {
        "status": status,
        "reason_code": reason_code,
        "note": note,
        "updated_at": timestamp,
    }
    record["last_checked_at"] = timestamp
    record["last_updated_at"] = timestamp
    record["audit"] = _append_audit(previous, record, action="resolve", timestamp=timestamp, note=note)
    records[api_key] = record

    waivers = {str(item.get("api_key")): dict(item) for item in waivers_payload.get("waivers", []) if item.get("api_key")}
    if status == "waived":
        waivers[api_key] = {
            "api_key": api_key,
            "reason_code": reason_code,
            "note": note,
            "updated_at": timestamp,
        }
    else:
        waivers.pop(api_key, None)

    next_state = dict(state_payload)
    next_state["records"] = [records[key] for key in sorted(records)]
    next_state["updated_at"] = timestamp
    next_state["last_run"] = {
        "mode": "resolve",
        "repo": ((state_payload.get("remote") or {}).get("repo")),
        "base_branch": ((state_payload.get("remote") or {}).get("base_branch")),
        "since_pr": ((state_payload.get("cursor") or {}).get("last_processed_pr_number")),
        "until_pr": ((state_payload.get("cursor") or {}).get("last_processed_pr_number")),
        "processed_pr_count": 0,
        "processed_pr_numbers": [],
        "full_rescan": False,
        "changed_files": [],
        "changes": diff_records({api_key: previous}, {api_key: record}),
    }

    next_waivers = {
        "schema_version": 2,
        "waivers": [waivers[key] for key in sorted(waivers)],
    }
    return next_state, next_waivers, record
