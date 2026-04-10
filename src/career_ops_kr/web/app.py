from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from career_ops_kr.commands.intake import DEFAULT_PROFILE_PATH, DEFAULT_SCORECARD_PATH
from career_ops_kr.commands.resume import (
    build_tailored_resume_from_url as run_build_tailored_resume_from_url,
)
from career_ops_kr.tracker import delete_tracker_row, parse_tracker_rows, upsert_tracker_row
from career_ops_kr.utils import ensure_dir, slugify
from career_ops_kr.web.artifacts import (
    artifact_slug,
    build_focus_preview,
    filter_generated_resume_items,
    generated_resume_snapshot,
    load_tailoring_guidance,
    output_url,
)
from career_ops_kr.web.common import (
    coerce_path,
    normalize_job_url as _normalize_job_url,
    safe_bool as _safe_bool,
    safe_int as _safe_int,
    safe_relative_to as _safe_relative_to,
    safe_text as _safe_text,
)
from career_ops_kr.web.dashboard import (
    default_web_profile_path,
    get_dashboard_snapshot,
    resolve_resume_preset,
    resume_preset_options,
    tracker_status_choices,
)
from career_ops_kr.web.db import (
    connection_scope,
    create_database_backup,
    export_database_snapshot,
    import_database_snapshot,
    resolve_db_path,
)
from career_ops_kr.web.resume_tools import (
    list_resumes,
    save_uploaded_resume,
)
from career_ops_kr.web.jobs_view import (
    describe_save_result,
    enrich_search_results,
    job_artifact_specs,
    job_attention_snapshot,
    job_row_api_payload,
    job_row_with_ui_state,
    job_tracker_sync_snapshot,
    load_tracker_row_for_job,
    matches_attention_filter,
    saved_job_search_state,
)
from career_ops_kr.web.live_smoke import (
    get_live_smoke_status_snapshot,
    new_db_export_path,
    web_db_snapshot_dir,
)
from career_ops_kr.web.job_records import (
    attach_resume_artifacts_to_job,
    bulk_update_job_records,
    delete_job_record,
    normalize_web_source,
    save_job_record,
    sync_tracker_rows_to_jobs,
    update_job_record,
)
from career_ops_kr.web.paths import WebPaths
from career_ops_kr.web.routers import (
    build_jobs_router,
    build_pages_router,
    build_resume_router,
    build_search_router,
    build_system_router,
)
from career_ops_kr.web.routers.deps import WebRouterDeps
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


def _web_paths() -> WebPaths:
    return WebPaths(
        repo_root=REPO_ROOT,
        output_dir=OUTPUT_DIR,
        tracker_path=TRACKER_PATH,
        jd_dir=JD_DIR,
        report_dir=REPORT_DIR,
        web_resume_output_dir=WEB_RESUME_OUTPUT_DIR,
        live_smoke_report_dir=LIVE_SMOKE_REPORT_DIR,
        web_db_output_dir=OUTPUT_DIR / "web-db",
    )


def _template_context(**kwargs: Any) -> dict[str, Any]:
    return kwargs


def _coerce_path(value: Any) -> Path | None:
    return coerce_path(value, repo_root=REPO_ROOT)


def _get_dashboard_snapshot() -> dict[str, Any]:
    return get_dashboard_snapshot(paths=_web_paths())


def _default_web_profile_path() -> Path:
    return default_web_profile_path(default_profile_path=DEFAULT_PROFILE_PATH, repo_root=REPO_ROOT)


def _tracker_status_choices() -> list[str]:
    return tracker_status_choices(repo_root=REPO_ROOT)


def _resume_preset_options() -> list[dict[str, str]]:
    return resume_preset_options(
        resume_presets=RESUME_PRESETS,
        template_presets=TEMPLATE_PRESETS,
    )


def _resolve_resume_preset(role_key: str, language: str) -> tuple[Path, Path]:
    return resolve_resume_preset(
        role_key,
        language,
        resume_presets=RESUME_PRESETS,
        template_presets=TEMPLATE_PRESETS,
    )


def _output_url(path: Path) -> str:
    return output_url(path, paths=_web_paths())


def _artifact_slug(company: str, position: str, role_key: str, language: str) -> str:
    return artifact_slug(company, position, role_key, language)


def _generated_resume_snapshot(*, limit: int | None = 6) -> dict[str, Any]:
    return generated_resume_snapshot(paths=_web_paths(), limit=limit)


def _filter_generated_resume_items(
    items: list[dict[str, Any]],
    *,
    source: str = "all",
    query: str = "",
) -> list[dict[str, Any]]:
    return filter_generated_resume_items(items, source=source, query=query)


def _load_tailoring_guidance(context_path: Path | None) -> dict[str, Any] | None:
    return load_tailoring_guidance(context_path, paths=_web_paths())


def _build_focus_preview(guidance: dict[str, Any] | None) -> dict[str, list[str]]:
    return build_focus_preview(guidance)


def _get_live_smoke_status_snapshot(*, max_age_hours: float = 48.0) -> dict[str, Any]:
    return get_live_smoke_status_snapshot(paths=_web_paths(), max_age_hours=max_age_hours)


def _web_db_snapshot_dir() -> Path:
    return web_db_snapshot_dir(paths=_web_paths())


def _new_db_export_path() -> Path:
    return new_db_export_path(paths=_web_paths())


def _job_attention_snapshot(job_row: dict[str, Any], tracker_row: dict[str, str] | None = None) -> dict[str, Any]:
    return job_attention_snapshot(job_row, paths=_web_paths(), tracker_row=tracker_row)


def _job_row_with_ui_state(job_row: dict[str, Any]) -> dict[str, Any]:
    return job_row_with_ui_state(job_row, paths=_web_paths())


def _job_row_api_payload(job_row: Any) -> dict[str, Any]:
    return job_row_api_payload(job_row, paths=_web_paths())


def _saved_job_search_state(
    job_row: dict[str, Any],
    *,
    match_note: str = "canonical URL 기준으로 이미 저장된 항목입니다.",
) -> dict[str, Any]:
    return saved_job_search_state(job_row, paths=_web_paths(), match_note=match_note)


def _describe_save_result(save_result: str) -> tuple[str, str, str]:
    return describe_save_result(save_result)


def _matches_attention_filter(row: dict[str, Any], attention: str | None) -> bool:
    return matches_attention_filter(row, attention)


def _job_tracker_sync_snapshot(job_row: dict[str, Any], tracker_row: dict[str, str] | None) -> list[str]:
    return job_tracker_sync_snapshot(job_row, tracker_row)


def _enrich_search_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return enrich_search_results(items, paths=_web_paths())


def _job_artifact_specs(job_row: dict[str, Any]) -> list[dict[str, Any]]:
    return job_artifact_specs(job_row, paths=_web_paths())


def _load_tracker_row_for_job(job_row: dict[str, Any]) -> dict[str, str] | None:
    return load_tracker_row_for_job(job_row, paths=_web_paths())


def _attach_resume_artifacts_to_job(
    *,
    artifacts: BuildTailoredResumeFromUrlArtifacts,
    job_id: int | None = None,
    url: str | None = None,
    company: str | None = None,
    position: str | None = None,
) -> int | None:
    return attach_resume_artifacts_to_job(
        artifacts=artifacts,
        connection_scope=connection_scope,
        normalize_job_url=_normalize_job_url,
        job_id=job_id,
        url=url,
        company=company,
        position=position,
    )


def _normalize_web_source(source: str | None, url: str) -> str | None:
    return normalize_web_source(source, url, safe_text=_safe_text)


def _save_job_record(payload: dict[str, Any]) -> dict[str, Any]:
    return save_job_record(
        payload,
        connection_scope=connection_scope,
        tracker_path=TRACKER_PATH,
        normalize_job_url=_normalize_job_url,
        safe_text=_safe_text,
        safe_int=_safe_int,
        safe_bool=_safe_bool,
        upsert_tracker_row=upsert_tracker_row,
        load_tracker_row_for_job=_load_tracker_row_for_job,
    )


def _update_job_record(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return update_job_record(
        job_id,
        payload,
        connection_scope=connection_scope,
        tracker_path=TRACKER_PATH,
        normalize_job_url=_normalize_job_url,
        safe_text=_safe_text,
        safe_int=_safe_int,
        safe_bool=_safe_bool,
        upsert_tracker_row=upsert_tracker_row,
        job_row_api_payload=_job_row_api_payload,
    )


def _delete_job_record(job_id: int) -> bool:
    return delete_job_record(
        job_id,
        connection_scope=connection_scope,
        tracker_path=TRACKER_PATH,
        safe_int=_safe_int,
        delete_tracker_row=delete_tracker_row,
    )


def _bulk_update_job_records(job_ids: list[Any], payload: dict[str, Any]) -> dict[str, Any]:
    return bulk_update_job_records(
        job_ids,
        payload,
        connection_scope=connection_scope,
        safe_int=_safe_int,
        safe_text=_safe_text,
        update_job_record=_update_job_record,
    )


def _sync_tracker_rows_to_jobs() -> dict[str, int]:
    return sync_tracker_rows_to_jobs(
        tracker_path=TRACKER_PATH,
        connection_scope=connection_scope,
        parse_tracker_rows=parse_tracker_rows,
    )


def _router_deps() -> WebRouterDeps:
    return WebRouterDeps(
        templates=templates,
        output_dir=OUTPUT_DIR,
        jd_dir=JD_DIR,
        report_dir=REPORT_DIR,
        web_resume_output_dir=WEB_RESUME_OUTPUT_DIR,
        default_web_scorecard_path=DEFAULT_WEB_SCORECARD_PATH,
        connection_scope=connection_scope,
        resolve_db_path=resolve_db_path,
        template_context=_template_context,
        get_dashboard_snapshot=_get_dashboard_snapshot,
        get_live_smoke_status_snapshot=_get_live_smoke_status_snapshot,
        resume_preset_options=_resume_preset_options,
        generated_resume_snapshot=_generated_resume_snapshot,
        filter_generated_resume_items=_filter_generated_resume_items,
        tracker_status_choices=_tracker_status_choices,
        job_row_with_ui_state=_job_row_with_ui_state,
        load_tracker_row_for_job=_load_tracker_row_for_job,
        load_tailoring_guidance=_load_tailoring_guidance,
        coerce_path=_coerce_path,
        job_attention_snapshot=_job_attention_snapshot,
        job_tracker_sync_snapshot=_job_tracker_sync_snapshot,
        job_artifact_specs=_job_artifact_specs,
        build_focus_preview=_build_focus_preview,
        safe_relative_to=_safe_relative_to,
        create_database_backup=create_database_backup,
        export_database_snapshot=export_database_snapshot,
        import_database_snapshot=import_database_snapshot,
        ensure_dir=ensure_dir,
        web_db_snapshot_dir=_web_db_snapshot_dir,
        new_db_export_path=_new_db_export_path,
        slugify=slugify,
        save_job_record=_save_job_record,
        safe_text=_safe_text,
        describe_save_result=_describe_save_result,
        saved_job_search_state=_saved_job_search_state,
        update_job_record=_update_job_record,
        bulk_update_job_records=_bulk_update_job_records,
        delete_job_record=_delete_job_record,
        sync_tracker_rows_to_jobs=_sync_tracker_rows_to_jobs,
        matches_attention_filter=_matches_attention_filter,
        search_jobs=lambda query: search_jobs(query),
        enrich_search_results=_enrich_search_results,
        default_web_profile_path=_default_web_profile_path,
        list_resumes=list_resumes,
        save_uploaded_resume=save_uploaded_resume,
        normalize_web_source=_normalize_web_source,
        resolve_resume_preset=_resolve_resume_preset,
        artifact_slug=_artifact_slug,
        run_build_tailored_resume_from_url=lambda *args, **kwargs: run_build_tailored_resume_from_url(*args, **kwargs),
        attach_resume_artifacts_to_job=_attach_resume_artifacts_to_job,
        safe_int=_safe_int,
        output_url=_output_url,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Career Ops KR Web")
    ensure_dir(OUTPUT_DIR)
    app.mount("/output", StaticFiles(directory=OUTPUT_DIR.as_posix()), name="output")
    deps = _router_deps()
    app.include_router(build_pages_router(deps))
    app.include_router(build_system_router(deps))
    app.include_router(build_jobs_router(deps))
    app.include_router(build_search_router(deps))
    app.include_router(build_resume_router(deps))
    return app
