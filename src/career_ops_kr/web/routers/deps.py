from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi.templating import Jinja2Templates


@dataclass(frozen=True, slots=True)
class PagesRouterDeps:
    templates: Jinja2Templates
    output_dir: Path
    jd_dir: Path
    report_dir: Path
    connection_scope: Callable[..., Any]
    resolve_db_path: Callable[..., Path]
    template_context: Callable[..., dict[str, Any]]
    get_dashboard_snapshot: Callable[[], dict[str, Any]]
    get_follow_up_agenda: Callable[..., dict[str, Any]]
    get_live_smoke_status_snapshot: Callable[..., dict[str, Any]]
    resume_preset_options: Callable[[], list[dict[str, str]]]
    generated_resume_snapshot: Callable[..., dict[str, Any]]
    filter_generated_resume_items: Callable[..., list[dict[str, Any]]]
    enrich_generated_resume_items: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    tracker_status_choices: Callable[[], list[str]]
    job_row_with_ui_state: Callable[[dict[str, Any]], dict[str, Any]]
    load_tracker_row_for_job: Callable[[dict[str, Any]], dict[str, str] | None]
    load_tailoring_guidance: Callable[[Path | None], dict[str, Any] | None]
    coerce_path: Callable[[Any], Path | None]
    job_attention_snapshot: Callable[[dict[str, Any], dict[str, str] | None], dict[str, Any]]
    job_tracker_sync_snapshot: Callable[[dict[str, Any], dict[str, str] | None], list[str]]
    job_artifact_specs: Callable[[dict[str, Any]], list[dict[str, Any]]]
    build_focus_preview: Callable[[dict[str, Any] | None], dict[str, list[str]]]
    safe_relative_to: Callable[[Path, Path], bool]
    list_resumes: Callable[[], list[dict[str, Any]]]
    list_search_presets: Callable[[], list[dict[str, Any]]]
    get_search_preset: Callable[[str], dict[str, Any] | None]
    use_search_preset: Callable[[str], dict[str, Any] | None]
    search_jobs: Callable[[str], dict[str, Any]]
    enrich_search_results: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class JobsRouterDeps:
    connection_scope: Callable[..., Any]
    get_follow_up_agenda: Callable[..., dict[str, Any]]
    job_row_with_ui_state: Callable[[dict[str, Any]], dict[str, Any]]
    save_job_record: Callable[[dict[str, Any]], dict[str, Any]]
    safe_text: Callable[[Any], str]
    describe_save_result: Callable[[str], tuple[str, str, str]]
    saved_job_search_state: Callable[..., dict[str, Any]]
    update_job_record: Callable[[int, dict[str, Any]], dict[str, Any]]
    bulk_update_job_records: Callable[[list[Any], dict[str, Any]], dict[str, Any]]
    delete_job_record: Callable[[int], bool]
    sync_tracker_rows_to_jobs: Callable[[], dict[str, int]]
    matches_attention_filter: Callable[[dict[str, Any], str | None], bool]


@dataclass(frozen=True, slots=True)
class SearchRouterDeps:
    search_jobs: Callable[[str], dict[str, Any]]
    enrich_search_results: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    list_search_presets: Callable[[], list[dict[str, Any]]]
    save_search_preset: Callable[[str | None, str | None, bool], dict[str, Any]]
    set_default_search_preset: Callable[[str], dict[str, Any]]
    delete_search_preset: Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class ResumeRouterDeps:
    output_dir: Path
    jd_dir: Path
    report_dir: Path
    web_resume_output_dir: Path
    default_web_scorecard_path: Path
    resume_preset_options: Callable[[], list[dict[str, str]]]
    default_web_profile_path: Callable[[], Path]
    list_resumes: Callable[[], list[dict[str, Any]]]
    save_uploaded_resume: Callable[[str, bytes], dict[str, Any]]
    normalize_web_source: Callable[[str | None, str], str | None]
    resolve_resume_preset: Callable[[str, str], tuple[Path, Path]]
    artifact_slug: Callable[[str, str, str, str], str]
    run_build_tailored_resume_from_url: Callable[..., Any]
    attach_resume_artifacts_to_job: Callable[..., int | None]
    safe_int: Callable[[Any], int | None]
    output_url: Callable[[Path], str]
    load_tailoring_guidance: Callable[[Path | None], dict[str, Any] | None]
    ensure_dir: Callable[[Path], None]


@dataclass(frozen=True, slots=True)
class SystemRouterDeps:
    resolve_db_path: Callable[..., Path]
    get_dashboard_snapshot: Callable[[], dict[str, Any]]
    get_live_smoke_status_snapshot: Callable[..., dict[str, Any]]
    create_database_backup: Callable[..., Path]
    export_database_snapshot: Callable[..., Path]
    import_database_snapshot: Callable[..., dict[str, Any]]
    ensure_dir: Callable[[Path], None]
    web_db_snapshot_dir: Callable[[], Path]
    new_db_export_path: Callable[[], Path]
    slugify: Callable[..., str]


@dataclass(frozen=True, slots=True)
class WebRouterDeps:
    pages: PagesRouterDeps
    jobs: JobsRouterDeps
    search: SearchRouterDeps
    resume: ResumeRouterDeps
    system: SystemRouterDeps

    @property
    def output_dir(self) -> Path:
        return self.pages.output_dir

    @property
    def web_resume_output_dir(self) -> Path:
        return self.resume.web_resume_output_dir
