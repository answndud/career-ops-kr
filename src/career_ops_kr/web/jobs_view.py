from __future__ import annotations

from datetime import datetime
from typing import Any

from career_ops_kr.tracker import parse_tracker_rows
from career_ops_kr.web.artifacts import (
    artifact_manifest_path_for_html,
    output_url,
)
from career_ops_kr.web.common import (
    coerce_path,
    normalize_job_url,
    parse_tracker_date,
    path_exists,
    safe_int,
    safe_text,
    safe_relative_to,
)
from career_ops_kr.web.db import connection_scope
from career_ops_kr.web.paths import WebPaths


def load_tracker_row_for_job(job_row: dict[str, Any], *, paths: WebPaths) -> dict[str, str] | None:
    if not paths.tracker_path.exists():
        return None
    tracker_rows = parse_tracker_rows(paths.tracker_path.read_text(encoding="utf-8"))
    tracker_id = safe_int(job_row.get("tracker_id"))
    for row in tracker_rows:
        if tracker_id is not None and safe_int(row.get("id")) == tracker_id:
            return row
    company = safe_text(job_row.get("company"))
    role = safe_text(job_row.get("position"))
    for row in tracker_rows:
        if safe_text(row.get("company")) == company and safe_text(row.get("role")) == role:
            return row
    return None


def job_attention_snapshot(
    job_row: dict[str, Any],
    *,
    paths: WebPaths,
    tracker_row: dict[str, str] | None = None,
) -> dict[str, Any]:
    tags: list[dict[str, str]] = []
    next_steps: list[str] = []

    if not path_exists(job_row.get("report_path"), repo_root=paths.repo_root):
        tags.append({"label": "리포트 없음", "tone": "warn"})
        next_steps.append("공고 평가 리포트를 먼저 생성하세요.")
    if not path_exists(job_row.get("html_path"), repo_root=paths.repo_root):
        tags.append({"label": "이력서 없음", "tone": "warn"})
        next_steps.append("맞춤 이력서 HTML/PDF를 생성하세요.")
    if tracker_row is None:
        tags.append({"label": "tracker 확인 필요", "tone": "warn"})
        next_steps.append("Markdown tracker row 연결을 확인하세요.")

    follow_up_date = parse_tracker_date(safe_text(job_row.get("follow_up")))
    if follow_up_date and follow_up_date < datetime.now().date():
        tags.insert(0, {"label": "팔로업 overdue", "tone": "error"})
        next_steps.insert(0, "팔로업 날짜가 지났습니다. 상태와 메모를 갱신하세요.")
    elif not follow_up_date and safe_text(job_row.get("status")) in {"검토중", "지원예정"}:
        tags.append({"label": "팔로업 미설정", "tone": "warn"})
        next_steps.append("다음 액션을 잊지 않도록 팔로업 날짜를 지정하세요.")

    if not next_steps:
        next_steps.append("현재 저장 상태는 안정적입니다. 필요하면 최신 공고 기준으로 이력서를 다시 생성하세요.")

    return {
        "tags": tags,
        "next_steps": next_steps,
        "summary": next_steps[0],
        "has_problem": any(tag["tone"] in {"warn", "error"} for tag in tags),
    }


def job_row_with_ui_state(job_row: dict[str, Any], *, paths: WebPaths) -> dict[str, Any]:
    row = dict(job_row)
    tracker_row = load_tracker_row_for_job(row, paths=paths)
    attention = job_attention_snapshot(row, paths=paths, tracker_row=tracker_row)
    row["tracker_row"] = tracker_row
    row["attention"] = attention
    row["artifact_summary"] = {
        "job": path_exists(row.get("job_path"), repo_root=paths.repo_root),
        "report": path_exists(row.get("report_path"), repo_root=paths.repo_root),
        "context": path_exists(row.get("context_path"), repo_root=paths.repo_root),
        "html": path_exists(row.get("html_path"), repo_root=paths.repo_root),
        "pdf": path_exists(row.get("pdf_path"), repo_root=paths.repo_root),
    }
    return row


def job_row_api_payload(job_row: Any, *, paths: WebPaths) -> dict[str, Any]:
    return job_row_with_ui_state(dict(job_row or {}), paths=paths)


def saved_job_search_state(
    job_row: dict[str, Any],
    *,
    paths: WebPaths,
    match_note: str = "canonical URL 기준으로 이미 저장된 항목입니다.",
) -> dict[str, Any]:
    ui_row = job_row_with_ui_state(job_row, paths=paths)
    return {
        "id": int(job_row["id"]),
        "status": safe_text(job_row.get("status")),
        "detail_url": f"/tracker/{int(job_row['id'])}",
        "has_report": ui_row["artifact_summary"]["report"],
        "has_resume": ui_row["artifact_summary"]["html"],
        "attention_summary": ui_row["attention"]["summary"],
        "match_note": match_note,
        "duplicate_guard_note": "같은 canonical URL로 다시 저장해도 기존 항목을 재사용합니다.",
    }


def describe_save_result(save_result: str) -> tuple[str, str, str]:
    if save_result == "updated":
        return (
            "기존 공고를 최신 정보로 보완했습니다",
            "같은 canonical URL의 기존 항목을 재사용하고 비어 있던 정보를 보완했습니다. 새 duplicate row는 만들지 않았습니다.",
            "ok",
        )
    if save_result == "existing":
        return (
            "이미 저장된 공고입니다",
            "같은 canonical URL과 일치해서 기존 항목을 그대로 다시 사용했습니다. 새 duplicate row는 만들지 않았습니다.",
            "warn",
        )
    return (
        "새 공고를 저장했습니다",
        "새 tracker 항목을 만들었습니다. 이후 같은 canonical URL을 다시 저장하면 기존 항목을 재사용합니다.",
        "ok",
    )


def matches_attention_filter(row: dict[str, Any], attention: str | None) -> bool:
    normalized = safe_text(attention).lower()
    if not normalized:
        return True
    if normalized == "missing-report":
        return not row["artifact_summary"]["report"]
    if normalized == "missing-resume":
        return not row["artifact_summary"]["html"]
    if normalized == "follow-up-overdue":
        return any(tag["label"] == "팔로업 overdue" for tag in row["attention"]["tags"])
    if normalized == "unlinked-tracker":
        return row["tracker_row"] is None
    return True


def job_tracker_sync_snapshot(job_row: dict[str, Any], tracker_row: dict[str, str] | None) -> list[str]:
    if tracker_row is None:
        return ["연결된 markdown tracker row가 없습니다."]
    warnings: list[str] = []
    if safe_int(job_row.get("tracker_id")) is None:
        warnings.append("web row에 tracker_id가 없습니다.")
    if safe_text(job_row.get("status")) != safe_text(tracker_row.get("status")):
        warnings.append("web 상태와 markdown tracker 상태가 다릅니다.")
    if safe_text(job_row.get("source")) != safe_text(tracker_row.get("source")):
        warnings.append("web 출처와 markdown tracker 출처가 다릅니다.")
    if safe_text(job_row.get("notes")) and safe_text(job_row.get("notes")) != safe_text(tracker_row.get("notes")):
        warnings.append("web 메모와 markdown tracker 메모가 다릅니다.")
    return warnings


def enrich_search_results(items: list[dict[str, Any]], *, paths: WebPaths) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    url_keys = {
        canonical
        for item in items
        if (canonical := normalize_job_url(item.get("url")))
    }
    rows_by_canonical: dict[str, dict[str, Any]] = {}
    if url_keys:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE canonical_url IS NOT NULL OR url IS NOT NULL
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
        for row in rows:
            canonical_url = safe_text(row.get("canonical_url")) or normalize_job_url(row.get("url"))
            if canonical_url and canonical_url not in rows_by_canonical:
                rows_by_canonical[canonical_url] = row
    for item in items:
        enriched_item = dict(item)
        canonical_url = normalize_job_url(item.get("url"))
        saved_row = rows_by_canonical.get(canonical_url or "")
        enriched_item["canonical_url"] = canonical_url
        if saved_row:
            enriched_item["saved_job"] = saved_job_search_state(saved_row, paths=paths)
        else:
            enriched_item["saved_job"] = None
        enriched.append(enriched_item)
    return enriched


def attach_generated_resume_job_signals(
    items: list[dict[str, Any]],
    *,
    paths: WebPaths,
) -> list[dict[str, Any]]:
    enriched_items = [dict(item) for item in items]
    linked_job_ids = sorted(
        {
            int(item["job_id"])
            for item in enriched_items
            if item.get("job_id") is not None
        }
    )
    generated_jobs_by_id: dict[int, dict[str, Any]] = {}
    if linked_job_ids:
        placeholders = ", ".join("?" for _ in linked_job_ids)
        with connection_scope() as conn:
            generated_job_rows = conn.execute(
                f"SELECT * FROM jobs WHERE id IN ({placeholders})",
                linked_job_ids,
            ).fetchall()
        generated_jobs_by_id = {
            int(row["id"]): job_row_with_ui_state(row, paths=paths)
            for row in generated_job_rows
        }
    for item in enriched_items:
        linked_job = generated_jobs_by_id.get(int(item["job_id"])) if item.get("job_id") is not None else None
        item["job_attention_summary"] = linked_job["attention"]["summary"] if linked_job else None
        item["job_attention_tags"] = linked_job["attention"]["tags"] if linked_job else []
        item["job_has_problem"] = bool(linked_job["attention"]["has_problem"]) if linked_job else False
    return enriched_items


def job_artifact_specs(job_row: dict[str, Any], *, paths: WebPaths) -> list[dict[str, Any]]:
    artifact_specs = [
        ("job_path", "저장된 JD", paths.jd_dir, "job"),
        ("report_path", "평가 리포트", paths.report_dir, "report"),
        ("tailoring_path", "Tailoring Packet", paths.output_dir / "resume-tailoring", None),
        ("context_path", "Resume Context", paths.output_dir / "resume-contexts", "context"),
        ("html_path", "Resume HTML", paths.output_dir, None),
        ("pdf_path", "Resume PDF", paths.output_dir, None),
    ]
    items: list[dict[str, Any]] = []
    for field, label, root, view_key in artifact_specs:
        path = coerce_path(job_row.get(field), repo_root=paths.repo_root)
        if path is None or not path.exists() or not safe_relative_to(path, root):
            continue
        item = {
            "field": field,
            "label": label,
            "path": path.as_posix(),
            "output_url": output_url(path, paths=paths) if field in {"html_path", "pdf_path"} else None,
            "view_url": f"/tracker/{job_row['id']}/artifacts/{view_key}" if view_key else None,
        }
        items.append(item)
    manifest_path = artifact_manifest_path_for_html(
        coerce_path(job_row.get("html_path"), repo_root=paths.repo_root)
    )
    if manifest_path and safe_relative_to(manifest_path, paths.output_dir):
        items.append(
            {
                "field": "manifest_path",
                "label": "Build Manifest",
                "path": manifest_path.as_posix(),
                "output_url": output_url(manifest_path, paths=paths),
                "view_url": None,
            }
        )
    return items
