from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from career_ops_kr.commands.resume import evaluate_live_smoke_report_health
from career_ops_kr.web.paths import WebPaths


def get_live_smoke_status_snapshot(*, paths: WebPaths, max_age_hours: float = 48.0) -> dict[str, Any]:
    if not paths.live_smoke_report_dir.exists():
        return {
            "available": False,
            "summary": "아직 저장된 live smoke report가 없습니다.",
            "counts": {},
            "problem_items": [],
            "latest_generated_at": None,
            "entries": [],
            "directory": paths.live_smoke_report_dir.as_posix(),
        }
    try:
        entries, scan_summary = evaluate_live_smoke_report_health(
            paths.live_smoke_report_dir,
            max_age_hours=max_age_hours,
        )
    except Exception as exc:
        return {
            "available": False,
            "summary": f"Live smoke 상태를 읽지 못했습니다: {exc}",
            "counts": {},
            "problem_items": [],
            "latest_generated_at": None,
            "entries": [],
            "directory": paths.live_smoke_report_dir.as_posix(),
        }
    counts: dict[str, int] = {}
    latest_generated_at: str | None = None
    for entry in entries:
        counts[entry.status] = counts.get(entry.status, 0) + 1
        if entry.generated_at and (latest_generated_at is None or entry.generated_at > latest_generated_at):
            latest_generated_at = entry.generated_at
    problem_items = [entry for entry in entries if entry.status != "ok"]
    if not entries:
        summary = "저장된 live smoke report는 있지만 target 상태가 없습니다."
    elif problem_items:
        summary = f"문제 target {len(problem_items)}개가 있습니다."
    else:
        summary = "모든 target의 최신 saved smoke 상태가 정상입니다."
    return {
        "available": bool(entries),
        "summary": summary,
        "counts": counts,
        "problem_items": problem_items[:4],
        "entries": entries[:6],
        "latest_generated_at": latest_generated_at,
        "recognized_report_count": scan_summary.get("recognized_count", 0),
        "ignored_count": len(scan_summary.get("ignored", [])),
        "max_age_hours": max_age_hours,
        "directory": paths.live_smoke_report_dir.as_posix(),
    }


def web_db_snapshot_dir(*, paths: WebPaths):
    return paths.web_db_output_dir


def new_db_export_path(*, paths: WebPaths):
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return web_db_snapshot_dir(paths=paths) / f"career-ops-web-export-{timestamp}.json"
