from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from career_ops_kr.commands.intake import DEFAULT_PROFILE_PATH, DEFAULT_SCORECARD_PATH
from career_ops_kr.commands.resume import build_tailored_resume_from_url as run_build_tailored_resume_from_url
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
SEARCH_SETTING_KEYS = ("ADZUNA_APP_ID", "ADZUNA_API_KEY")


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
    if url and "adzuna" not in url:
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


def _generated_resume_snapshot(*, limit: int = 6) -> dict[str, Any]:
    if not WEB_RESUME_OUTPUT_DIR.exists():
        return {"total": 0, "items": []}

    html_paths = sorted(
        WEB_RESUME_OUTPUT_DIR.glob("*.html"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    items: list[dict[str, Any]] = []
    for html_path in html_paths[:limit]:
        pdf_path = html_path.with_suffix(".pdf")
        job_path = JD_DIR / f"{html_path.stem}.md"
        report_path = REPORT_DIR / f"{html_path.stem}.md"
        context_path = OUTPUT_DIR / "resume-contexts" / f"{html_path.stem}.json"
        modified_at = datetime.fromtimestamp(html_path.stat().st_mtime, UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        items.append(
            {
                "label": html_path.name,
                "html_path": html_path.as_posix(),
                "html_url": _output_url(html_path),
                "pdf_path": pdf_path.as_posix() if pdf_path.exists() else None,
                "pdf_url": _output_url(pdf_path) if pdf_path.exists() else None,
                "job_path": job_path.as_posix() if job_path.exists() else None,
                "report_path": report_path.as_posix() if report_path.exists() else None,
                "context_path": context_path.as_posix() if context_path.exists() else None,
                "modified_at": modified_at,
            }
        )
    return {"total": len(html_paths), "items": items}


def _web_db_snapshot_dir() -> Path:
    return WEB_DB_OUTPUT_DIR


def _new_db_export_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _web_db_snapshot_dir() / f"career-ops-web-export-{timestamp}.json"


def _coerce_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value)


def _safe_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


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
    with connection_scope() as conn:
        row = None
        if job_id is not None:
            row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None and url:
            row = conn.execute(
                "SELECT id FROM jobs WHERE url = ? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
                (url,),
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
            SET job_path = ?, report_path = ?, tailoring_path = ?, context_path = ?, html_path = ?, pdf_path = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
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
    if normalized in {"efinancial", "adzuna"}:
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
    return {
        "company": company,
        "position": position,
        "url": _safe_text(payload.get("url")) or None,
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
    tracker_row = upsert_tracker_row(TRACKER_PATH, _tracker_row_from_job_payload(normalized))
    tracker_id = int(tracker_row["id"])
    with connection_scope() as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs(
                company, position, url, status, notes, date_applied, follow_up,
                salary_min, salary_max, location, remote, source, tracker_id
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["company"],
                normalized["position"],
                normalized["url"],
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
    return row or {}


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
            ),
        )

    @app.get("/tracker", response_class=HTMLResponse)
    def tracker_page(request: Request) -> HTMLResponse:
        with connection_scope() as conn:
            jobs = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        return templates.TemplateResponse(
            request,
            "tracker.html",
            _template_context(
                jobs=jobs,
                dashboard=_get_dashboard_snapshot(),
                statuses=_tracker_status_choices(),
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
        return templates.TemplateResponse(
            request,
            "job-detail.html",
            _template_context(
                job=row,
                tracker_row=_load_tracker_row_for_job(row),
                artifacts=_job_artifact_specs(row),
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
        return _get_dashboard_snapshot()

    @app.get("/api/jobs")
    def api_list_jobs(
        status: str | None = None,
        q: str | None = None,
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
            return conn.execute(query, params).fetchall()

    @app.post("/api/jobs", status_code=201)
    async def api_create_job(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            return _save_job_record(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/import", status_code=201)
    async def api_import_job(request: Request) -> dict[str, Any]:
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
            return _save_job_record(import_payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
            return search_jobs(q.strip())
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
            "profile_path": profile_path.as_posix(),
            "base_context_path": base_context_path.as_posix(),
            "template_path": template_path.as_posix(),
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
