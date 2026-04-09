from __future__ import annotations

import os
import re
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from career_ops_kr.commands.intake import DEFAULT_PROFILE_PATH, DEFAULT_SCORECARD_PATH
from career_ops_kr.commands.resume import (
    build_tailored_resume_from_url as run_build_tailored_resume_from_url,
    evaluate_live_smoke_report_health,
    load_resume_artifact_manifest,
)
from career_ops_kr.portals import canonicalize_job_url
from career_ops_kr.tracker import delete_tracker_row, parse_tracker_rows, upsert_tracker_row
from career_ops_kr.utils import ensure_dir, load_yaml, slugify
from career_ops_kr.web.ai import (
    ALLOWED_SETTING_KEYS,
    AiServiceError,
    ai_feature_enabled,
    generate_json,
    load_settings,
    resolve_provider,
    store_setting,
)
from career_ops_kr.web.db import (
    connection_scope,
    create_database_backup,
    export_database_snapshot,
    import_database_snapshot,
    resolve_db_path,
)
from career_ops_kr.web.resume_tools import (
    analyze_resume_match,
    generate_assistant_output,
    list_resumes,
    recommend_jobs_for_resume,
    rewrite_resume_for_job,
    save_uploaded_resume,
)
from career_ops_kr.web.search import search_jobs


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATE_DIR.as_posix())
OUTPUT_DIR = Path(os.getenv("CAREER_OPS_WEB_OUTPUT_DIR", (REPO_ROOT / "output").as_posix()))
TRACKER_PATH = Path(os.getenv("CAREER_OPS_WEB_TRACKER_PATH", (REPO_ROOT / "data" / "applications.md").as_posix()))
JD_DIR = Path(os.getenv("CAREER_OPS_WEB_JD_DIR", (REPO_ROOT / "jds").as_posix()))
REPORT_DIR = Path(os.getenv("CAREER_OPS_WEB_REPORT_DIR", (REPO_ROOT / "reports").as_posix()))
WEB_RESUME_OUTPUT_DIR = Path(
    os.getenv("CAREER_OPS_WEB_RESUME_OUTPUT_DIR", (OUTPUT_DIR / "web-resumes").as_posix())
)
LIVE_SMOKE_REPORT_DIR = Path(
    os.getenv("CAREER_OPS_WEB_LIVE_SMOKE_DIR", (OUTPUT_DIR / "live-smoke").as_posix())
)
DEFAULT_WEB_SCORECARD_PATH = (
    DEFAULT_SCORECARD_PATH if DEFAULT_SCORECARD_PATH.exists() else REPO_ROOT / "config" / "scorecard.kr.yml"
)
RESUME_PRESETS: dict[tuple[str, str], Path] = {
    ("backend", "ko"): REPO_ROOT / "examples" / "resume-context.backend.ko.example.json",
    ("backend", "en"): REPO_ROOT / "examples" / "resume-context.backend.example.json",
    ("platform", "ko"): REPO_ROOT / "examples" / "resume-context.platform.ko.example.json",
    ("platform", "en"): REPO_ROOT / "examples" / "resume-context.platform.example.json",
    ("data-platform", "ko"): REPO_ROOT / "examples" / "resume-context.data-platform.ko.example.json",
    ("data-platform", "en"): REPO_ROOT / "examples" / "resume-context.data-platform.example.json",
    ("data-ai", "ko"): REPO_ROOT / "examples" / "resume-context.data-ai.ko.example.json",
    ("data-ai", "en"): REPO_ROOT / "examples" / "resume-context.data-ai.example.json",
}
TEMPLATE_PRESETS: dict[str, Path] = {
    "ko": REPO_ROOT / "templates" / "resume-ko.html",
    "en": REPO_ROOT / "templates" / "resume-en.html",
}
WEB_DB_OUTPUT_DIR = OUTPUT_DIR / "web-db"
AI_SETTING_KEYS = ("AI_PROVIDER", "GEMINI_API_KEY", "OPENAI_API_KEY")
SEARCH_SETTING_KEYS: tuple[str, ...] = ()


def _strip_html(value: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "on"} else 0


def _ai_enabled() -> bool:
    return ai_feature_enabled()


def _require_ai_enabled() -> None:
    if not _ai_enabled():
        raise HTTPException(status_code=404, detail="AI features are disabled.")


def _template_context(**kwargs: Any) -> dict[str, Any]:
    return {"ai_enabled": _ai_enabled(), **kwargs}


def _latest_resume_content() -> str:
    with connection_scope() as conn:
        row = conn.execute("SELECT content FROM resumes ORDER BY created_at DESC LIMIT 1").fetchone()
    return str(row["content"]) if row else ""


def _analyze_job_listing(payload: dict[str, Any]) -> dict[str, Any]:
    url = str(payload.get("url") or "")
    page_content = ""
    if url:
        try:
            response = httpx.get(url, timeout=10.0, follow_redirects=True)
            response.raise_for_status()
            page_content = _strip_html(response.text)[:5000]
        except httpx.HTTPError:
            page_content = ""

    resume_content = _latest_resume_content()
    prompt = (
        "당신은 전문 채용 분석가입니다. 아래 채용 공고를 분석하고 JSON으로 답하세요.\n\n"
        f"채용 제목: {payload.get('title')}\n"
        f"회사: {payload.get('company')}\n"
        f"위치: {payload.get('location')}\n"
        f"출처: {payload.get('source')}\n"
        f"{'채용 페이지 내용: ' + page_content if page_content else ''}\n\n"
        f"{'지원자 이력서: ' + resume_content if resume_content else ''}\n\n"
        'Return JSON like {"requirements":[],"match_score":null,"analysis":"","improvements":[]}'
    )
    return generate_json(prompt)


def _get_dashboard_snapshot() -> dict[str, Any]:
    with connection_scope() as conn:
        total_jobs = conn.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]
        total_resumes = conn.execute("SELECT COUNT(*) AS count FROM resumes").fetchone()["count"]
        total_ai_outputs = conn.execute("SELECT COUNT(*) AS count FROM ai_outputs").fetchone()["count"]
        status_counts = conn.execute(
            "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status ORDER BY status"
        ).fetchall()
        recent_jobs = conn.execute(
            "SELECT id, company, position, status, updated_at FROM jobs ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        follow_ups = conn.execute(
            """
            SELECT id, company, position, follow_up
            FROM jobs
            WHERE follow_up IS NOT NULL AND follow_up >= date('now')
            ORDER BY follow_up ASC
            LIMIT 5
            """
        ).fetchall()
        recent_resumes = conn.execute(
            "SELECT id, filename, created_at FROM resumes ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        recent_ai_outputs = conn.execute(
            """
            SELECT id, type, output, created_at
            FROM ai_outputs
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()
    generated_outputs = _generated_resume_snapshot(limit=6)
    return {
        "totalJobs": total_jobs,
        "totalResumes": total_resumes,
        "totalAiOutputs": total_ai_outputs,
        "statusCounts": status_counts,
        "recentJobs": recent_jobs,
        "upcomingFollowUps": follow_ups,
        "recentResumes": recent_resumes,
        "generatedResumeCount": generated_outputs["total"],
        "generatedWebResumeCount": generated_outputs["web_total"],
        "generatedCliResumeCount": generated_outputs["cli_total"],
        "recentGeneratedResumes": generated_outputs["items"],
        "recentAiOutputs": [
            {
                "id": row["id"],
                "type": row["type"],
                "created_at": row["created_at"],
                "preview": _safe_text(row["output"])[:220],
            }
            for row in recent_ai_outputs
        ],
        "activeProvider": _safe_provider_name(),
    }


def _default_web_profile_path() -> Path:
    if DEFAULT_PROFILE_PATH.exists():
        return DEFAULT_PROFILE_PATH
    return REPO_ROOT / "config" / "profile.example.yml"


def _tracker_status_choices() -> list[str]:
    states = load_yaml(REPO_ROOT / "config" / "states.yml")
    canonical = states.get("canonical", [])
    return [str(value) for value in canonical if str(value).strip()]


def _resume_preset_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    role_labels = {
        "backend": "Backend",
        "platform": "Platform",
        "data-platform": "Data-Platform",
        "data-ai": "Data-AI",
    }
    language_labels = {"ko": "한국어", "en": "English"}
    for (role_key, language), context_path in RESUME_PRESETS.items():
        template_path = TEMPLATE_PRESETS[language]
        options.append(
            {
                "key": f"{role_key}:{language}",
                "role_key": role_key,
                "role_label": role_labels.get(role_key, role_key),
                "language": language,
                "language_label": language_labels.get(language, language),
                "context_path": context_path.as_posix(),
                "template_path": template_path.as_posix(),
            }
        )
    return options


def _resolve_resume_preset(role_key: str, language: str) -> tuple[Path, Path]:
    normalized_role = role_key.strip().lower()
    normalized_language = language.strip().lower()
    context_path = RESUME_PRESETS.get((normalized_role, normalized_language))
    if context_path is None:
        raise ValueError(f"Unsupported resume preset: role={role_key}, language={language}")
    return context_path, TEMPLATE_PRESETS[normalized_language]


def _output_url(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return path.as_posix()
    return f"/output/{relative.as_posix()}"


def _artifact_slug(company: str, position: str, role_key: str, language: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    basis = f"{company}-{position}-{role_key}-{language}"
    return f"{timestamp}-{slugify(basis, fallback='web-resume')}"


def _generated_resume_snapshot(*, limit: int | None = 6) -> dict[str, Any]:
    if not OUTPUT_DIR.exists():
        return {"total": 0, "items": []}

    linked_rows_by_path: dict[str, dict[str, Any]] = {}
    with connection_scope() as conn:
        job_rows = conn.execute(
            """
            SELECT id, company, position, job_path, report_path, context_path, html_path, pdf_path
            FROM jobs
            WHERE job_path IS NOT NULL OR report_path IS NOT NULL OR context_path IS NOT NULL
               OR html_path IS NOT NULL OR pdf_path IS NOT NULL
            """
        ).fetchall()
    for row in job_rows:
        for field in ("job_path", "report_path", "context_path", "html_path", "pdf_path"):
            path = _coerce_path(row.get(field))
            if path is None:
                continue
            try:
                linked_rows_by_path[path.resolve().as_posix()] = row
            except FileNotFoundError:
                continue

    items: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    cli_total = 0
    web_total = 0
    manifest_total = 0
    legacy_total = 0

    manifest_paths = sorted(
        [path for path in OUTPUT_DIR.rglob("*.manifest.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifest_paths:
        manifest = _load_artifact_manifest(manifest_path)
        if manifest is None:
            continue
        manifest_paths_payload = manifest.get("paths") or {}
        if not isinstance(manifest_paths_payload, dict):
            continue
        html_path = _coerce_path(manifest_paths_payload.get("html_path"))
        if html_path is None or not html_path.exists() or not _safe_relative_to(html_path, OUTPUT_DIR):
            continue
        resolved_html = html_path.resolve().as_posix()
        if resolved_html in seen_paths:
            continue
        seen_paths.add(resolved_html)

        pdf_path = _coerce_path(manifest_paths_payload.get("pdf_path"))
        report_path = _coerce_path(manifest_paths_payload.get("report_path"))
        job_path = _coerce_path(manifest_paths_payload.get("job_path"))
        context_path = _coerce_path(manifest_paths_payload.get("context_path"))
        linked_row = None
        for candidate_path in (html_path, pdf_path, job_path, report_path, context_path):
            if candidate_path is None:
                continue
            try:
                linked_row = linked_rows_by_path.get(candidate_path.resolve().as_posix())
            except FileNotFoundError:
                linked_row = None
            if linked_row is not None:
                break

        source_label = "web" if _safe_relative_to(html_path, WEB_RESUME_OUTPUT_DIR) else "cli"
        if source_label == "web":
            web_total += 1
        else:
            cli_total += 1
        manifest_total += 1

        guidance = _guidance_from_artifact_manifest(manifest) or _load_tailoring_guidance(context_path)
        modified_at = datetime.fromtimestamp(html_path.stat().st_mtime, UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        manifest_job = manifest.get("job") if isinstance(manifest.get("job"), dict) else {}
        selection = manifest.get("selection") if isinstance(manifest.get("selection"), dict) else {}
        items.append(
            {
                "label": html_path.name,
                "source_label": source_label,
                "provenance": "manifest",
                "provenance_label": "manifest",
                "build_pipeline": _safe_text(manifest.get("pipeline")),
                "manifest_path": manifest_path.as_posix(),
                "manifest_url": _output_url(manifest_path),
                "html_path": html_path.as_posix(),
                "html_url": _output_url(html_path),
                "pdf_path": pdf_path.as_posix() if pdf_path and pdf_path.exists() else None,
                "pdf_url": _output_url(pdf_path) if pdf_path and pdf_path.exists() else None,
                "job_path": job_path.as_posix() if job_path and job_path.exists() else None,
                "report_path": report_path.as_posix() if report_path and report_path.exists() else None,
                "context_path": context_path.as_posix() if context_path and context_path.exists() else None,
                "job_id": int(linked_row["id"]) if linked_row else None,
                "job_detail_url": f"/tracker/{int(linked_row['id'])}" if linked_row else None,
                "company": _safe_text(linked_row.get("company")) if linked_row else _safe_text(manifest_job.get("company")),
                "position": _safe_text(linked_row.get("position")) if linked_row else _safe_text(manifest_job.get("title")),
                "guidance": guidance,
                "focus_preview": _build_focus_preview(guidance),
                "modified_at": modified_at,
                "selected_role_profile": _safe_text(selection.get("selected_role_profile")),
            }
        )

    html_paths = sorted(
        [path for path in OUTPUT_DIR.rglob("*.html") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for html_path in html_paths:
        resolved_html = html_path.resolve().as_posix()
        if resolved_html in seen_paths:
            continue
        seen_paths.add(resolved_html)
        pdf_path = html_path.with_suffix(".pdf")
        derived_job_path = JD_DIR / f"{html_path.stem}.md"
        derived_report_path = REPORT_DIR / f"{html_path.stem}.md"
        derived_context_path = OUTPUT_DIR / "resume-contexts" / f"{html_path.stem}.json"
        linked_row = linked_rows_by_path.get(resolved_html)
        if linked_row is None and pdf_path.exists():
            linked_row = linked_rows_by_path.get(pdf_path.resolve().as_posix())
        job_path = _coerce_path(linked_row.get("job_path")) if linked_row else None
        report_path = _coerce_path(linked_row.get("report_path")) if linked_row else None
        context_path = _coerce_path(linked_row.get("context_path")) if linked_row else None
        if job_path is None:
            job_path = derived_job_path
        if report_path is None:
            report_path = derived_report_path
        if context_path is None:
            context_path = derived_context_path
        source_label = "web" if _safe_relative_to(html_path, WEB_RESUME_OUTPUT_DIR) else "cli"
        if source_label == "web":
            web_total += 1
        else:
            cli_total += 1
        legacy_total += 1
        guidance = _load_tailoring_guidance(context_path)
        modified_at = datetime.fromtimestamp(html_path.stat().st_mtime, UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        items.append(
            {
                "label": html_path.name,
                "source_label": source_label,
                "provenance": "legacy",
                "provenance_label": "legacy",
                "build_pipeline": "",
                "manifest_path": None,
                "manifest_url": None,
                "html_path": html_path.as_posix(),
                "html_url": _output_url(html_path),
                "pdf_path": pdf_path.as_posix() if pdf_path.exists() else None,
                "pdf_url": _output_url(pdf_path) if pdf_path.exists() else None,
                "job_path": job_path.as_posix() if job_path.exists() else None,
                "report_path": report_path.as_posix() if report_path.exists() else None,
                "context_path": context_path.as_posix() if context_path.exists() else None,
                "job_id": int(linked_row["id"]) if linked_row else None,
                "job_detail_url": f"/tracker/{int(linked_row['id'])}" if linked_row else None,
                "company": _safe_text(linked_row.get("company")) if linked_row else "",
                "position": _safe_text(linked_row.get("position")) if linked_row else "",
                "guidance": guidance,
                "focus_preview": _build_focus_preview(guidance),
                "modified_at": modified_at,
            }
        )
    return {
        "total": len(items),
        "web_total": web_total,
        "cli_total": cli_total,
        "manifest_total": manifest_total,
        "legacy_total": legacy_total,
        "items": items[:limit] if limit is not None else items,
    }


def _filter_generated_resume_items(
    items: list[dict[str, Any]],
    *,
    source: str = "all",
    query: str = "",
) -> list[dict[str, Any]]:
    normalized_source = source.strip().lower()
    normalized_query = query.strip().lower()
    filtered: list[dict[str, Any]] = []
    for item in items:
        if normalized_source in {"web", "cli"} and item.get("source_label") != normalized_source:
            continue
        if normalized_query:
            haystack = " ".join(
                [
                    str(item.get("label") or ""),
                    str(item.get("company") or ""),
                    str(item.get("position") or ""),
                    str(item.get("html_path") or ""),
                    str(item.get("job_path") or ""),
                    str(item.get("report_path") or ""),
                    str(item.get("manifest_path") or ""),
                    str(item.get("build_pipeline") or ""),
                ]
            ).lower()
            if normalized_query not in haystack:
                continue
        filtered.append(item)
    return filtered


def _load_tailoring_guidance(context_path: Path | None) -> dict[str, Any] | None:
    if context_path is None or not context_path.exists():
        return None
    if not _safe_relative_to(context_path, OUTPUT_DIR / "resume-contexts"):
        return None
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    guidance = payload.get("tailoringGuidance")
    return guidance if isinstance(guidance, dict) else None


def _build_focus_preview(guidance: dict[str, Any] | None) -> dict[str, list[str]]:
    if not guidance:
        return {"skills": [], "experience": [], "notes": []}
    focus = guidance.get("focus")
    if not isinstance(focus, dict):
        return {"skills": [], "experience": [], "notes": []}
    return {
        "skills": [str(item) for item in (focus.get("skills_to_emphasize") or [])[:4]],
        "experience": [str(item) for item in (focus.get("experience_focus") or [])[:3]],
        "notes": [str(item) for item in (focus.get("notes") or [])[:3]],
    }


def _get_live_smoke_status_snapshot(*, max_age_hours: float = 48.0) -> dict[str, Any]:
    if not LIVE_SMOKE_REPORT_DIR.exists():
        return {
            "available": False,
            "summary": "아직 저장된 live smoke report가 없습니다.",
            "counts": {},
            "problem_items": [],
            "latest_generated_at": None,
            "entries": [],
            "directory": LIVE_SMOKE_REPORT_DIR.as_posix(),
        }
    try:
        entries, scan_summary = evaluate_live_smoke_report_health(
            LIVE_SMOKE_REPORT_DIR,
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
            "directory": LIVE_SMOKE_REPORT_DIR.as_posix(),
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
        "directory": LIVE_SMOKE_REPORT_DIR.as_posix(),
    }


def _web_db_snapshot_dir() -> Path:
    return WEB_DB_OUTPUT_DIR


def _new_db_export_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _web_db_snapshot_dir() / f"career-ops-web-export-{timestamp}.json"


def _coerce_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _artifact_manifest_path_for_html(html_path: Path | None) -> Path | None:
    if html_path is None:
        return None
    manifest_path = html_path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        return None
    return manifest_path


def _load_artifact_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists() or not _safe_relative_to(path, OUTPUT_DIR):
        return None
    try:
        return load_resume_artifact_manifest(path)
    except (ValueError, json.JSONDecodeError, OSError):
        return None


def _guidance_from_artifact_manifest(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manifest:
        return None
    selection = manifest.get("selection")
    focus = manifest.get("focus")
    normalized_selection = selection if isinstance(selection, dict) else {}
    normalized_focus = focus if isinstance(focus, dict) else {}
    if not normalized_selection and not normalized_focus:
        return None
    return {
        "selection": normalized_selection,
        "focus": normalized_focus,
    }


def _normalize_job_url(url: str | None) -> str | None:
    normalized = _safe_text(url)
    if not normalized:
        return None
    return canonicalize_job_url(normalized)


def _path_exists(value: Any) -> bool:
    path = _coerce_path(value)
    return bool(path and path.exists())


def _safe_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _parse_tracker_date(value: str | None) -> date | None:
    raw_value = _safe_text(value)
    if not raw_value:
        return None
    try:
        return date.fromisoformat(raw_value[:10])
    except ValueError:
        return None


def _job_attention_snapshot(job_row: dict[str, Any], tracker_row: dict[str, str] | None = None) -> dict[str, Any]:
    tags: list[dict[str, str]] = []
    next_steps: list[str] = []

    if not _path_exists(job_row.get("report_path")):
        tags.append({"label": "리포트 없음", "tone": "warn"})
        next_steps.append("공고 평가 리포트를 먼저 생성하세요.")
    if not _path_exists(job_row.get("html_path")):
        tags.append({"label": "이력서 없음", "tone": "warn"})
        next_steps.append("맞춤 이력서 HTML/PDF를 생성하세요.")
    if tracker_row is None:
        tags.append({"label": "tracker 확인 필요", "tone": "warn"})
        next_steps.append("Markdown tracker row 연결을 확인하세요.")

    follow_up_date = _parse_tracker_date(_safe_text(job_row.get("follow_up")))
    if follow_up_date and follow_up_date < datetime.now().date():
        tags.insert(0, {"label": "팔로업 overdue", "tone": "error"})
        next_steps.insert(0, "팔로업 날짜가 지났습니다. 상태와 메모를 갱신하세요.")
    elif not follow_up_date and _safe_text(job_row.get("status")) in {"검토중", "지원예정"}:
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


def _job_row_with_ui_state(job_row: dict[str, Any]) -> dict[str, Any]:
    row = dict(job_row)
    tracker_row = _load_tracker_row_for_job(row)
    attention = _job_attention_snapshot(row, tracker_row)
    row["tracker_row"] = tracker_row
    row["attention"] = attention
    row["artifact_summary"] = {
        "job": _path_exists(row.get("job_path")),
        "report": _path_exists(row.get("report_path")),
        "context": _path_exists(row.get("context_path")),
        "html": _path_exists(row.get("html_path")),
        "pdf": _path_exists(row.get("pdf_path")),
    }
    return row


def _saved_job_search_state(
    job_row: dict[str, Any],
    *,
    match_note: str = "canonical URL 기준으로 이미 저장된 항목입니다.",
) -> dict[str, Any]:
    ui_row = _job_row_with_ui_state(job_row)
    return {
        "id": int(job_row["id"]),
        "status": _safe_text(job_row.get("status")),
        "detail_url": f"/tracker/{int(job_row['id'])}",
        "has_report": ui_row["artifact_summary"]["report"],
        "has_resume": ui_row["artifact_summary"]["html"],
        "attention_summary": ui_row["attention"]["summary"],
        "match_note": match_note,
        "duplicate_guard_note": "같은 canonical URL로 다시 저장해도 기존 항목을 재사용합니다.",
    }


def _describe_save_result(save_result: str) -> tuple[str, str, str]:
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


def _matches_attention_filter(row: dict[str, Any], attention: str | None) -> bool:
    normalized = _safe_text(attention).lower()
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


def _job_tracker_sync_snapshot(job_row: dict[str, Any], tracker_row: dict[str, str] | None) -> list[str]:
    if tracker_row is None:
        return ["연결된 markdown tracker row가 없습니다."]
    warnings: list[str] = []
    if _safe_int(job_row.get("tracker_id")) is None:
        warnings.append("web row에 tracker_id가 없습니다.")
    if _safe_text(job_row.get("status")) != _safe_text(tracker_row.get("status")):
        warnings.append("web 상태와 markdown tracker 상태가 다릅니다.")
    if _safe_text(job_row.get("notes")) and _safe_text(job_row.get("notes")) != _safe_text(tracker_row.get("notes")):
        warnings.append("web 메모와 markdown tracker 메모가 다릅니다.")
    return warnings


def _enrich_search_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    url_keys = {
        canonical
        for item in items
        if (canonical := _normalize_job_url(item.get("url")))
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
            canonical_url = _safe_text(row.get("canonical_url")) or _normalize_job_url(row.get("url"))
            if canonical_url and canonical_url not in rows_by_canonical:
                rows_by_canonical[canonical_url] = row
    for item in items:
        enriched_item = dict(item)
        canonical_url = _normalize_job_url(item.get("url"))
        saved_row = rows_by_canonical.get(canonical_url or "")
        enriched_item["canonical_url"] = canonical_url
        if saved_row:
            enriched_item["saved_job"] = _saved_job_search_state(saved_row)
        else:
            enriched_item["saved_job"] = None
        enriched.append(enriched_item)
    return enriched


def _job_artifact_specs(job_row: dict[str, Any]) -> list[dict[str, Any]]:
    artifact_specs = [
        ("job_path", "저장된 JD", JD_DIR, "job"),
        ("report_path", "평가 리포트", REPORT_DIR, "report"),
        ("tailoring_path", "Tailoring Packet", OUTPUT_DIR / "resume-tailoring", None),
        ("context_path", "Resume Context", OUTPUT_DIR / "resume-contexts", "context"),
        ("html_path", "Resume HTML", OUTPUT_DIR, None),
        ("pdf_path", "Resume PDF", OUTPUT_DIR, None),
    ]
    items: list[dict[str, Any]] = []
    for field, label, root, view_key in artifact_specs:
        path = _coerce_path(job_row.get(field))
        if path is None or not path.exists() or not _safe_relative_to(path, root):
            continue
        item = {
            "field": field,
            "label": label,
            "path": path.as_posix(),
            "output_url": _output_url(path) if field in {"html_path", "pdf_path"} else None,
            "view_url": f"/tracker/{job_row['id']}/artifacts/{view_key}" if view_key else None,
        }
        items.append(item)
    manifest_path = _artifact_manifest_path_for_html(_coerce_path(job_row.get("html_path")))
    if manifest_path and _safe_relative_to(manifest_path, OUTPUT_DIR):
        items.append(
            {
                "field": "manifest_path",
                "label": "Build Manifest",
                "path": manifest_path.as_posix(),
                "output_url": _output_url(manifest_path),
                "view_url": None,
            }
        )
    return items


def _load_tracker_row_for_job(job_row: dict[str, Any]) -> dict[str, str] | None:
    if not TRACKER_PATH.exists():
        return None
    tracker_rows = parse_tracker_rows(TRACKER_PATH.read_text(encoding="utf-8"))
    tracker_id = _safe_int(job_row.get("tracker_id"))
    for row in tracker_rows:
        if tracker_id is not None and _safe_int(row.get("id")) == tracker_id:
            return row
    company = _safe_text(job_row.get("company"))
    role = _safe_text(job_row.get("position"))
    for row in tracker_rows:
        if _safe_text(row.get("company")) == company and _safe_text(row.get("role")) == role:
            return row
    return None


def _attach_resume_artifacts_to_job(
    *,
    artifacts: BuildTailoredResumeFromUrlArtifacts,
    job_id: int | None = None,
    url: str | None = None,
    company: str | None = None,
    position: str | None = None,
) -> int | None:
    normalized_url = _normalize_job_url(url)
    with connection_scope() as conn:
        row = None
        if job_id is not None:
            row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None and normalized_url:
            row = conn.execute(
                """
                SELECT id FROM jobs
                WHERE canonical_url = ? OR url = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (normalized_url, normalized_url),
            ).fetchone()
        if row is None and company and position:
            row = conn.execute(
                """
                SELECT id FROM jobs
                WHERE company = ? AND position = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (company, position),
            ).fetchone()
        if row is None:
            return None
        matched_job_id = int(row["id"])
        conn.execute(
            """
            UPDATE jobs
            SET canonical_url = COALESCE(canonical_url, ?),
                job_path = ?, report_path = ?, tailoring_path = ?, context_path = ?, html_path = ?, pdf_path = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                normalized_url,
                artifacts.job_path.as_posix(),
                artifacts.report_path.as_posix(),
                artifacts.tailoring_path.as_posix(),
                artifacts.tailored_context_path.as_posix(),
                artifacts.html_path.as_posix(),
                artifacts.pdf_path.as_posix() if artifacts.pdf_path else None,
                matched_job_id,
            ),
        )
        conn.commit()
        return matched_job_id


def _normalize_web_source(source: str | None, url: str) -> str | None:
    normalized = _safe_text(source).lower()
    if normalized in {"원티드", "wanted"}:
        return "wanted"
    if normalized in {"사람인", "saramin"}:
        return "saramin"
    if normalized in {"리멤버", "remember"}:
        return "remember"
    if normalized in {"점핏", "jumpit"}:
        return "jumpit"
    if normalized == "efinancial":
        return None
    if "wanted.co.kr" in url:
        return "wanted"
    if "saramin.co.kr" in url:
        return "saramin"
    if "rememberapp.co.kr" in url:
        return "remember"
    if "jumpit.saramin.co.kr" in url or "jumpit" in url:
        return "jumpit"
    return None


def _normalize_job_payload(payload: dict[str, Any], *, default_status: str = "검토중") -> dict[str, Any]:
    company = _safe_text(payload.get("company"))
    position = _safe_text(payload.get("position") or payload.get("title"))
    if not company or not position:
        raise ValueError("Company and position are required")
    canonical_url = _normalize_job_url(payload.get("url"))
    return {
        "company": company,
        "position": position,
        "url": canonical_url,
        "canonical_url": canonical_url,
        "status": _safe_text(payload.get("status")) or default_status,
        "notes": _safe_text(payload.get("notes")) or None,
        "date_applied": _safe_text(payload.get("date_applied")) or None,
        "follow_up": _safe_text(payload.get("follow_up")) or None,
        "salary_min": _safe_int(payload.get("salary_min")),
        "salary_max": _safe_int(payload.get("salary_max")),
        "location": _safe_text(payload.get("location")) or None,
        "remote": _safe_bool(payload.get("remote")),
        "source": _safe_text(payload.get("source")) or "web",
    }


def _tracker_row_from_job_payload(
    payload: dict[str, Any],
    *,
    tracker_id: int | None = None,
    existing_row: dict[str, str] | None = None,
) -> dict[str, str]:
    row = {
        "date": _safe_text(payload.get("date_applied")) or _safe_text((existing_row or {}).get("date")),
        "company": _safe_text(payload.get("company")),
        "role": _safe_text(payload.get("position")),
        "score": _safe_text((existing_row or {}).get("score")),
        "status": _safe_text(payload.get("status")) or _safe_text((existing_row or {}).get("status")) or "검토중",
        "source": _safe_text(payload.get("source")) or _safe_text((existing_row or {}).get("source")) or "web",
        "resume": _safe_text((existing_row or {}).get("resume")),
        "report": _safe_text((existing_row or {}).get("report")),
        "notes": _safe_text(payload.get("notes")) or _safe_text((existing_row or {}).get("notes")),
    }
    if tracker_id is not None:
        row["id"] = str(tracker_id)
    return row


def _save_job_record(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_job_payload(payload)
    with connection_scope() as conn:
        existing = None
        canonical_url = normalized["canonical_url"]
        if canonical_url:
            rows = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE canonical_url = ? OR url = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (canonical_url, canonical_url),
            ).fetchall()
            for row in rows:
                existing = row
                break

        if existing:
            merged_payload = dict(existing)
            update_values: dict[str, Any] = {}
            for field in (
                "url",
                "canonical_url",
                "location",
                "salary_min",
                "salary_max",
                "date_applied",
                "follow_up",
            ):
                if not existing.get(field) and normalized.get(field):
                    update_values[field] = normalized[field]
            if normalized["notes"] and not _safe_text(existing.get("notes")):
                update_values["notes"] = normalized["notes"]
            if normalized["source"] and _safe_text(existing.get("source")) in {"", "web"}:
                if _safe_text(existing.get("source")) != normalized["source"]:
                    update_values["source"] = normalized["source"]
            if normalized["status"] and _safe_text(existing.get("status")) in {"", "검토중"}:
                if _safe_text(existing.get("status")) != normalized["status"]:
                    update_values["status"] = normalized["status"]

            merged_payload.update(update_values)
            tracker_row = upsert_tracker_row(
                TRACKER_PATH,
                _tracker_row_from_job_payload(
                    _normalize_job_payload(merged_payload, default_status=str(existing.get("status") or "검토중")),
                    tracker_id=_safe_int(existing.get("tracker_id")),
                    existing_row=_load_tracker_row_for_job(existing),
                ),
            )
            update_values["tracker_id"] = int(tracker_row["id"])
            if update_values:
                fields = [f"{field} = ?" for field in update_values]
                values = list(update_values.values())
                values.append(existing["id"])
                conn.execute(
                    f"UPDATE jobs SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
                    values,
                )
                conn.commit()
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (existing["id"],)).fetchone()
            result = dict(row or {})
            result["_save_result"] = "updated" if any(
                key != "tracker_id" for key in update_values
            ) else "existing"
            return result

        tracker_row = upsert_tracker_row(TRACKER_PATH, _tracker_row_from_job_payload(normalized))
        tracker_id = int(tracker_row["id"])
        cursor = conn.execute(
            """
            INSERT INTO jobs(
                company, position, url, canonical_url, status, notes, date_applied, follow_up,
                salary_min, salary_max, location, remote, source, tracker_id
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["company"],
                normalized["position"],
                normalized["url"],
                normalized["canonical_url"],
                normalized["status"],
                normalized["notes"],
                normalized["date_applied"],
                normalized["follow_up"],
                normalized["salary_min"],
                normalized["salary_max"],
                normalized["location"],
                normalized["remote"],
                normalized["source"],
                tracker_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    result = dict(row or {})
    result["_save_result"] = "created"
    return result


def _update_job_record(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    with connection_scope() as conn:
        existing = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")

        merged = dict(existing)
        merged.update(payload)
        normalized = _normalize_job_payload(merged, default_status=str(existing.get("status") or "검토중"))
        tracker_row = upsert_tracker_row(
            TRACKER_PATH,
            _tracker_row_from_job_payload(
                normalized,
                tracker_id=_safe_int(existing.get("tracker_id")),
            ),
        )
        tracker_id = int(tracker_row["id"])

        allowed_fields = {
            "company": normalized["company"],
            "position": normalized["position"],
            "url": normalized["url"],
            "canonical_url": normalized["canonical_url"],
            "status": normalized["status"],
            "notes": normalized["notes"],
            "date_applied": normalized["date_applied"],
            "follow_up": normalized["follow_up"],
            "salary_min": normalized["salary_min"],
            "salary_max": normalized["salary_max"],
            "location": normalized["location"],
            "remote": normalized["remote"],
            "source": normalized["source"],
        }
        fields: list[str] = []
        values: list[Any] = []
        for key in allowed_fields:
            if key not in payload:
                continue
            fields.append(f"{key} = ?")
            values.append(allowed_fields[key])
        fields.append("tracker_id = ?")
        values.append(tracker_id)

        if len(fields) == 1:
            raise HTTPException(status_code=400, detail="No fields to update")

        fields.append("updated_at = datetime('now')")
        values.append(job_id)
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row or {}


def _delete_job_record(job_id: int) -> bool:
    with connection_scope() as conn:
        existing = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not existing:
            return False
        tracker_id = _safe_int(existing.get("tracker_id"))
        if tracker_id is not None:
            delete_tracker_row(TRACKER_PATH, tracker_id)
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    return True


def _sync_tracker_rows_to_jobs() -> dict[str, int]:
    if not TRACKER_PATH.exists():
        return {"total": 0, "created": 0, "updated": 0}
    rows = parse_tracker_rows(TRACKER_PATH.read_text(encoding="utf-8"))
    created = 0
    updated = 0
    with connection_scope() as conn:
        for row in rows:
            tracker_id = int(row["id"])
            existing = conn.execute(
                """
                SELECT * FROM jobs
                WHERE tracker_id = ?
                   OR (company = ? AND position = ?)
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (tracker_id, row["company"], row["role"]),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE jobs
                    SET company = ?, position = ?, status = ?, date_applied = ?, notes = ?, source = ?, tracker_id = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        row["company"],
                        row["role"],
                        row["status"],
                        row["date"],
                        row["notes"],
                        row["source"],
                        tracker_id,
                        existing["id"],
                    ),
                )
                updated += 1
                continue
            conn.execute(
                """
                INSERT INTO jobs(
                    company, position, status, notes, date_applied, remote, source, tracker_id
                )
                VALUES(?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    row["company"],
                    row["role"],
                    row["status"],
                    row["notes"] or None,
                    row["date"] or None,
                    row["source"] or "tracker",
                    tracker_id,
                ),
            )
            created += 1
        conn.commit()
    return {"total": len(rows), "created": created, "updated": updated}


def create_app() -> FastAPI:
    app = FastAPI(title="Career Ops KR Web")
    ensure_dir(OUTPUT_DIR)
    app.mount("/output", StaticFiles(directory=OUTPUT_DIR.as_posix()), name="output")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "home.html",
            _template_context(
                dashboard=_get_dashboard_snapshot(),
                live_smoke=_get_live_smoke_status_snapshot(),
                provider=_safe_provider_name(),
                resume_presets=_resume_preset_options(),
            ),
        )

    @app.get("/search", response_class=HTMLResponse)
    def search_page(
        request: Request,
        q: str | None = None,
        source: str = "전체",
    ) -> HTMLResponse:
        results: dict[str, Any] | None = None
        visible_results: list[dict[str, Any]] = []
        active_source = source or "전체"
        if q:
            try:
                results = search_jobs(q)
                results["results"] = _enrich_search_results(results.get("results", []))
                source_counts = results.get("sources", {})
                if active_source != "전체" and active_source not in source_counts:
                    active_source = "전체"
                result_rows = results.get("results", [])
                visible_results = (
                    result_rows
                    if active_source == "전체"
                    else [row for row in result_rows if row.get("source") == active_source]
                )
            except Exception as exc:
                results = {"error": str(exc), "results": [], "sources": {}}
        return templates.TemplateResponse(
            request,
            "search.html",
            _template_context(
                query=q or "",
                results=results,
                visible_results=visible_results,
                active_source=active_source,
                provider=_safe_provider_name(),
                resume_presets=_resume_preset_options(),
            ),
        )

    @app.get("/artifacts", response_class=HTMLResponse)
    def artifacts_page(
        request: Request,
        source: str = "all",
        q: str = "",
    ) -> HTMLResponse:
        inventory = _generated_resume_snapshot(limit=None)
        filtered_items = _filter_generated_resume_items(inventory["items"], source=source, query=q)
        return templates.TemplateResponse(
            request,
            "artifacts.html",
            _template_context(
                source_filter=source if source in {"all", "web", "cli"} else "all",
                query=q,
                artifacts=filtered_items,
                inventory_total=inventory["total"],
                inventory_web_total=inventory["web_total"],
                inventory_cli_total=inventory["cli_total"],
                inventory_manifest_total=inventory["manifest_total"],
                inventory_legacy_total=inventory["legacy_total"],
                live_smoke=_get_live_smoke_status_snapshot(),
            ),
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "settings.html",
            _template_context(
                settings=load_settings(),
                allowed_ai_keys=[key for key in AI_SETTING_KEYS if key in ALLOWED_SETTING_KEYS],
                allowed_search_keys=[key for key in SEARCH_SETTING_KEYS if key in ALLOWED_SETTING_KEYS],
                active_provider=_safe_provider_name(),
                db_path=resolve_db_path().as_posix(),
                live_smoke=_get_live_smoke_status_snapshot(),
            ),
        )

    @app.get("/tracker", response_class=HTMLResponse)
    def tracker_page(request: Request) -> HTMLResponse:
        with connection_scope() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        jobs = [_job_row_with_ui_state(row) for row in rows]
        attention_counts = {
            "missing_report": sum(1 for row in jobs if not row["artifact_summary"]["report"]),
            "missing_resume": sum(1 for row in jobs if not row["artifact_summary"]["html"]),
            "overdue_follow_up": sum(
                1 for row in jobs if any(tag["label"] == "팔로업 overdue" for tag in row["attention"]["tags"])
            ),
        }
        return templates.TemplateResponse(
            request,
            "tracker.html",
            _template_context(
                jobs=jobs,
                dashboard=_get_dashboard_snapshot(),
                statuses=_tracker_status_choices(),
                attention_counts=attention_counts,
                attention_filters=[
                    ("missing-report", "리포트 없음"),
                    ("missing-resume", "이력서 없음"),
                    ("follow-up-overdue", "팔로업 overdue"),
                    ("unlinked-tracker", "tracker 미연결"),
                ],
            ),
        )

    @app.get("/tracker/{job_id}", response_class=HTMLResponse)
    def tracker_job_detail_page(request: Request, job_id: int) -> HTMLResponse:
        with connection_scope() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            match_results = conn.execute(
                """
                SELECT id, resume_id, match_score, created_at
                FROM match_results
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (job_id,),
            ).fetchall()
            ai_outputs = conn.execute(
                """
                SELECT id, type, output, created_at
                FROM ai_outputs
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (job_id,),
            ).fetchall()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        tracker_row = _load_tracker_row_for_job(row)
        tailoring_guidance = _load_tailoring_guidance(_coerce_path(row.get("context_path")))
        return templates.TemplateResponse(
            request,
            "job-detail.html",
            _template_context(
                job=row,
                tracker_row=tracker_row,
                attention=_job_attention_snapshot(row, tracker_row),
                tracker_sync=_job_tracker_sync_snapshot(row, tracker_row),
                artifacts=_job_artifact_specs(row),
                tailoring_guidance=tailoring_guidance,
                focus_preview=_build_focus_preview(tailoring_guidance),
                match_results=match_results,
                ai_outputs=[
                    {
                        "id": item["id"],
                        "type": item["type"],
                        "created_at": item["created_at"],
                        "preview": _safe_text(item["output"])[:220],
                    }
                    for item in ai_outputs
                ],
                resume_presets=_resume_preset_options(),
                statuses=_tracker_status_choices(),
            ),
        )

    @app.get("/tracker/{job_id}/artifacts/{artifact_key}")
    def tracker_job_artifact(job_id: int, artifact_key: str) -> Response:
        if artifact_key not in {"job", "report", "context"}:
            raise HTTPException(status_code=404, detail="Unsupported artifact")
        with connection_scope() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        field_map = {
            "job": ("job_path", JD_DIR, "text/markdown; charset=utf-8"),
            "report": ("report_path", REPORT_DIR, "text/markdown; charset=utf-8"),
            "context": ("context_path", OUTPUT_DIR / "resume-contexts", "application/json"),
        }
        field_name, root, media_type = field_map[artifact_key]
        path = _coerce_path(row.get(field_name))
        if path is None or not path.exists() or not _safe_relative_to(path, root):
            raise HTTPException(status_code=404, detail="Artifact not found")
        content = path.read_text(encoding="utf-8")
        if media_type == "application/json":
            return Response(content=content, media_type=media_type)
        return PlainTextResponse(content, media_type=media_type)

    @app.get("/resume", response_class=HTMLResponse)
    def resume_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "resume.html",
            _template_context(
                resumes=list_resumes(),
                resume_presets=_resume_preset_options(),
            ),
        )

    @app.get("/assistant", response_class=HTMLResponse)
    def assistant_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "assistant.html",
            _template_context(
                resumes=list_resumes(),
                modes=["cover_letter", "interview_prep", "job_analysis", "skill_gap"],
            ),
        )

    @app.get("/api/settings")
    def api_get_settings() -> dict[str, Any]:
        settings = load_settings()
        masked: dict[str, Any] = {}
        for key in sorted(ALLOWED_SETTING_KEYS):
            value = settings.get(key)
            if key.endswith("API_KEY") and value:
                masked[key] = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
                masked[f"{key}_set"] = True
            elif value:
                masked[key] = value
        masked["active_provider"] = _safe_provider_name()
        masked["ai_enabled"] = _ai_enabled()
        masked["db_path"] = resolve_db_path().as_posix()
        return masked

    @app.post("/api/settings")
    async def api_save_settings(request: Request) -> dict[str, bool]:
        payload = await request.json()
        key = str(payload.get("key") or "")
        value = payload.get("value")
        if key not in ALLOWED_SETTING_KEYS:
            raise HTTPException(status_code=400, detail="Invalid key")
        store_setting(key, None if value in {None, ""} else str(value))
        return {"success": True}

    @app.post("/api/system/db/backup")
    def api_backup_database() -> dict[str, str]:
        backup_path = create_database_backup(backup_dir=_web_db_snapshot_dir())
        return {"backup_path": backup_path.as_posix()}

    @app.post("/api/system/db/export")
    def api_export_database() -> dict[str, str]:
        export_path = export_database_snapshot(out_path=_new_db_export_path())
        return {"export_path": export_path.as_posix()}

    @app.post("/api/system/db/import")
    async def api_import_database(file: UploadFile = File(...)) -> dict[str, Any]:
        if not (file.filename or "").lower().endswith(".json"):
            raise HTTPException(status_code=400, detail="Only JSON snapshot files are supported.")
        ensure_dir(_web_db_snapshot_dir())
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = _web_db_snapshot_dir() / (
            f"import-{timestamp}-{slugify(file.filename or 'snapshot', fallback='snapshot')}.json"
        )
        snapshot_path.write_bytes(await file.read())
        try:
            result = import_database_snapshot(snapshot_path, backup_dir=_web_db_snapshot_dir())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "import_path": snapshot_path.as_posix(),
            "backup_path": str(result["backup_path"]),
            "counts": result["counts"],
        }

    @app.get("/api/dashboard")
    def api_dashboard() -> dict[str, Any]:
        dashboard = _get_dashboard_snapshot()
        dashboard["liveSmoke"] = _get_live_smoke_status_snapshot()
        return dashboard

    @app.get("/api/jobs")
    def api_list_jobs(
        status: str | None = None,
        q: str | None = None,
        attention: str | None = None,
        sort: str = "updated_at",
        order: str = "DESC",
    ) -> list[dict[str, Any]]:
        allowed_sorts = {
            "company",
            "position",
            "status",
            "date_applied",
            "source",
            "updated_at",
            "created_at",
        }
        sort_key = sort if sort in allowed_sorts else "updated_at"
        order_key = "ASC" if order.upper() == "ASC" else "DESC"
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if q:
            like = f"%{q}%"
            query += " AND (company LIKE ? OR position LIKE ? OR notes LIKE ?)"
            params.extend([like, like, like])
        query += f" ORDER BY {sort_key} {order_key}"
        with connection_scope() as conn:
            rows = conn.execute(query, params).fetchall()
        ui_rows = [_job_row_with_ui_state(row) for row in rows]
        return [row for row in ui_rows if _matches_attention_filter(row, attention)]

    @app.post("/api/jobs", status_code=201)
    async def api_create_job(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            return _save_job_record(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/import", status_code=201)
    async def api_import_job(request: Request, response: Response) -> dict[str, Any]:
        payload = await request.json()
        import_payload = {
            "company": payload.get("company"),
            "position": payload.get("position") or payload.get("title"),
            "url": payload.get("url"),
            "location": payload.get("location"),
            "salary_min": payload.get("salary_min"),
            "salary_max": payload.get("salary_max"),
            "notes": payload.get("description") or payload.get("notes"),
            "source": payload.get("source"),
            "status": payload.get("status") or "검토중",
        }
        try:
            saved = _save_job_record(import_payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_result = _safe_text(saved.pop("_save_result")) or "created"
        save_result_label, save_detail, save_tone = _describe_save_result(save_result)
        saved_state = _saved_job_search_state(
            saved,
            match_note="canonical URL 기준으로 저장 상태를 다시 확인했습니다.",
        )
        response.status_code = 201 if save_result == "created" else 200
        saved["save_result"] = save_result
        saved["save_result_label"] = save_result_label
        saved["save_detail"] = save_detail
        saved["save_tone"] = save_tone
        saved["detail_url"] = saved_state["detail_url"]
        saved["has_report"] = saved_state["has_report"]
        saved["has_resume"] = saved_state["has_resume"]
        saved["attention_summary"] = saved_state["attention_summary"]
        saved["duplicate_guard_note"] = saved_state["duplicate_guard_note"]
        saved["duplicate_guard_triggered"] = save_result in {"updated", "existing"}
        return saved

    @app.get("/api/jobs/{job_id}")
    def api_get_job(job_id: int) -> dict[str, Any]:
        with connection_scope() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return row

    @app.put("/api/jobs/{job_id}")
    async def api_update_job(job_id: int, request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            return _update_job_record(job_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/jobs/{job_id}")
    def api_delete_job(job_id: int) -> dict[str, bool]:
        if not _delete_job_record(job_id):
            raise HTTPException(status_code=404, detail="Not found")
        return {"success": True}

    @app.post("/api/tracker/sync")
    def api_sync_tracker() -> dict[str, int]:
        return _sync_tracker_rows_to_jobs()

    @app.get("/api/search")
    def api_search(q: str) -> dict[str, Any]:
        if not q.strip():
            raise HTTPException(status_code=400, detail="Query required")
        try:
            payload = search_jobs(q.strip())
            payload["results"] = _enrich_search_results(payload.get("results", []))
            return payload
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/search/analyze")
    async def api_search_analyze(request: Request) -> dict[str, Any]:
        _require_ai_enabled()
        payload = await request.json()
        try:
            return _analyze_job_listing(payload)
        except AiServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/resume/presets")
    def api_resume_presets() -> dict[str, Any]:
        return {
            "presets": _resume_preset_options(),
            "default_profile_path": _default_web_profile_path().as_posix(),
        }

    @app.get("/api/resume/upload")
    def api_list_resumes() -> list[dict[str, Any]]:
        return list_resumes()

    @app.post("/api/resume/upload", status_code=201)
    async def api_upload_resume(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        try:
            return save_uploaded_resume(file.filename or "resume.pdf", content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/resume/match")
    async def api_resume_match(request: Request) -> dict[str, Any]:
        _require_ai_enabled()
        payload = await request.json()
        resume_id = payload.get("resume_id")
        job_description = str(payload.get("job_description") or "")
        if not resume_id or not job_description:
            raise HTTPException(status_code=400, detail="resume_id and job_description are required")
        try:
            return analyze_resume_match(
                resume_id=int(resume_id),
                job_description=job_description,
                job_id=payload.get("job_id"),
            )
        except (ValueError, AiServiceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/resume/rewrite")
    async def api_resume_rewrite(request: Request) -> dict[str, Any]:
        _require_ai_enabled()
        payload = await request.json()
        job_description = str(payload.get("job_description") or "")
        if not job_description:
            raise HTTPException(status_code=400, detail="job_description is required")
        try:
            rewritten = rewrite_resume_for_job(
                job_description=job_description,
                company=payload.get("company"),
                position=payload.get("position"),
                language=str(payload.get("language") or "en"),
                resume_id=int(payload["resume_id"]) if payload.get("resume_id") else None,
            )
        except (ValueError, AiServiceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"rewritten_resume": rewritten}

    @app.post("/api/resume/recommend")
    async def api_resume_recommend(request: Request) -> dict[str, Any]:
        _require_ai_enabled()
        payload = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            payload = await request.json()
        try:
            return recommend_jobs_for_resume(
                resume_id=int(payload["resume_id"]) if payload.get("resume_id") else None
            )
        except (ValueError, AiServiceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/resume/build-from-url")
    async def api_resume_build_from_url(request: Request) -> dict[str, Any]:
        payload = await request.json()
        url = str(payload.get("url") or "").strip()
        company = str(payload.get("company") or "").strip() or "Unknown"
        position = str(payload.get("position") or "").strip() or "Resume"
        role_key = str(payload.get("role") or "platform").strip().lower()
        language = str(payload.get("language") or "ko").strip().lower()
        source = _normalize_web_source(payload.get("source"), url)
        want_pdf = bool(payload.get("pdf"))
        if not url:
            raise HTTPException(status_code=400, detail="url is required")

        try:
            base_context_path, template_path = _resolve_resume_preset(role_key, language)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        profile_path = _default_web_profile_path()
        slug = _artifact_slug(company, position, role_key, language)
        ensure_dir(WEB_RESUME_OUTPUT_DIR)
        job_out = JD_DIR / f"{slug}.md"
        report_out = REPORT_DIR / f"{slug}.md"
        tailoring_out = OUTPUT_DIR / "resume-tailoring" / f"{slug}.json"
        context_out = OUTPUT_DIR / "resume-contexts" / f"{slug}.json"
        html_out = WEB_RESUME_OUTPUT_DIR / f"{slug}.html"
        pdf_out = WEB_RESUME_OUTPUT_DIR / f"{slug}.pdf" if want_pdf else None

        try:
            artifacts = run_build_tailored_resume_from_url(
                url,
                base_context_path,
                template_path,
                source=source,
                job_out=job_out,
                report_out=report_out,
                tracker_out=None,
                html_out=html_out,
                tailoring_out=tailoring_out,
                tailored_context_out=context_out,
                pdf_out=pdf_out,
                profile_path=profile_path,
                scorecard_path=DEFAULT_WEB_SCORECARD_PATH,
                overwrite=False,
                insecure=False,
                pdf_format="A4",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        linked_job_id = _attach_resume_artifacts_to_job(
            artifacts=artifacts,
            job_id=_safe_int(payload.get("job_id")),
            url=url,
            company=company,
            position=position,
        )

        return {
            "job_id": linked_job_id,
            "job_path": artifacts.job_path.as_posix(),
            "report_path": artifacts.report_path.as_posix(),
            "tailoring_path": artifacts.tailoring_path.as_posix(),
            "context_path": artifacts.tailored_context_path.as_posix(),
            "html_path": artifacts.html_path.as_posix(),
            "html_url": _output_url(artifacts.html_path),
            "pdf_path": artifacts.pdf_path.as_posix() if artifacts.pdf_path else None,
            "pdf_url": _output_url(artifacts.pdf_path) if artifacts.pdf_path else None,
            "manifest_path": artifacts.manifest_path.as_posix() if artifacts.manifest_path else None,
            "manifest_url": _output_url(artifacts.manifest_path) if artifacts.manifest_path else None,
            "profile_path": profile_path.as_posix(),
            "base_context_path": base_context_path.as_posix(),
            "template_path": template_path.as_posix(),
            "tailoring_guidance": _load_tailoring_guidance(artifacts.tailored_context_path),
        }

    @app.post("/api/ai/{mode}")
    async def api_assistant(mode: str, request: Request) -> dict[str, str]:
        _require_ai_enabled()
        payload = await request.json()
        mode_map = {
            "cover-letter": "cover_letter",
            "interview-prep": "interview_prep",
            "analyze-job": "job_analysis",
            "skill-gap": "skill_gap",
        }
        normalized_mode = mode_map.get(mode)
        if normalized_mode is None:
            raise HTTPException(status_code=404, detail="Unsupported assistant mode")
        try:
            output = generate_assistant_output(mode=normalized_mode, payload=payload)
        except (ValueError, AiServiceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"output": output}

    return app


def _safe_provider_name() -> str:
    if not _ai_enabled():
        return "disabled"
    try:
        return resolve_provider().provider
    except AiServiceError:
        return "not configured"
