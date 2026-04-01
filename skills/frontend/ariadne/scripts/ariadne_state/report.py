"""Markdown report rendering for Ariadne v2."""

from __future__ import annotations

from typing import Any

from .models import STATUSES
from .state import summarize_records


def _render_table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")


def render_markdown(state_payload: dict[str, Any], waivers_payload: dict[str, Any]) -> str:
    summary = summarize_records(state_payload.get("records", []))
    last_run = dict(state_payload.get("last_run") or {})
    remote = dict(state_payload.get("remote") or {})
    lines = ["# Ariadne API Parity Report", ""]
    processed_numbers = list(last_run.get("processed_pr_numbers") or [])
    pr_range = "-"
    if processed_numbers:
        pr_range = f"#{processed_numbers[0]} -> #{processed_numbers[-1]}"
    elif last_run.get("until_pr") is not None:
        pr_range = f"#{last_run.get('until_pr')}"

    lines.extend(
        [
            "## 검증 컨텍스트",
            f"- 실행 모드: {last_run.get('mode') or 'unknown'}",
            f"- 원격 저장소: {last_run.get('repo') or remote.get('repo') or '-'}",
            f"- 기준 브랜치: {last_run.get('base_branch') or remote.get('base_branch') or '-'}",
            f"- 처리 PR 범위: {pr_range}",
            f"- 처리 PR 수: {last_run.get('processed_pr_count') or 0}",
            f"- 전체 재스캔 여부: {'yes' if last_run.get('full_rescan') else 'no'}",
            f"- 변경 파일 수: {len(last_run.get('changed_files') or [])}",
            "",
        ]
    )

    lines.append("## 요약")
    _render_table(lines, ["상태", "개수"], [[status, str(summary["status_counts"][status])] for status in STATUSES])
    lines.append("")

    changes = list(last_run.get("changes") or [])
    lines.append("## 이번 실행에서 바뀐 API")
    if changes:
        _render_table(
            lines,
            ["api_key", "이전 상태", "현재 상태", "reason_code"],
            [
                [
                    str(item.get("api_key") or ""),
                    str(item.get("previous_status") or "-"),
                    str(item.get("status") or "-"),
                    str(item.get("reason_code") or "-"),
                ]
                for item in changes
            ],
        )
    else:
        lines.append("- 없음")
    lines.append("")

    action_items = [
        record
        for record in state_payload.get("records", [])
        if str(record.get("status") or "") in ("missing", "mismatch", "needs-review")
    ]
    lines.append("## 조치 필요 항목")
    if action_items:
        _render_table(
            lines,
            ["api_key", "status", "reason_code", "frontend_evidence"],
            [
                [
                    str(record.get("api_key") or ""),
                    str(record.get("status") or ""),
                    str(record.get("reason_code") or ""),
                    ", ".join(
                        f"{item.get('file')}:{item.get('line')}"
                        for item in list(record.get("frontend_evidence") or [])[:3]
                    )
                    or "-",
                ]
                for record in action_items
            ],
        )
    else:
        lines.append("- 없음")
    lines.append("")

    waiver_rows = list(waivers_payload.get("waivers") or [])
    lines.append("## waiver 항목")
    if waiver_rows:
        _render_table(
            lines,
            ["api_key", "note", "updated_at"],
            [
                [
                    str(item.get("api_key") or ""),
                    str(item.get("note") or item.get("reason_code") or ""),
                    str(item.get("updated_at") or ""),
                ]
                for item in waiver_rows
            ],
        )
    else:
        lines.append("- 없음")

    lines.append("")
    return "\n".join(lines)
