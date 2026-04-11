from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from career_ops_kr.commands.intake import DEFAULT_PROFILE_PATH
from career_ops_kr.commands.resume import BuildTailoredResumeFromUrlArtifacts
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
    safe_text as _safe_text,
)
from career_ops_kr.web.dashboard import (
    attach_generated_resume_job_signals,
    default_web_profile_path,
    get_follow_up_agenda,
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
from career_ops_kr.web.job_records import (
    attach_resume_artifacts_to_job,
    bulk_update_job_records,
    delete_job_record,
    normalize_web_source,
    save_job_record,
    sync_tracker_rows_to_jobs,
    update_job_record,
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
from career_ops_kr.web.resume_tools import list_resumes, save_uploaded_resume
from career_ops_kr.web.search_presets import (
    delete_search_preset,
    get_search_preset,
    list_search_presets,
    save_search_preset,
    set_default_search_preset,
    use_search_preset,
)

if TYPE_CHECKING:
    from career_ops_kr.web.paths import WebPaths
    from career_ops_kr.web.router_deps_factory import WebRouterFactoryHooks


class WebRouterBindings:
    def __init__(self, hooks: WebRouterFactoryHooks):
        self.hooks = hooks

    def current_paths(self) -> WebPaths:
        return self.hooks.paths_factory()

    def template_context(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def coerce_repo_path(self, value: Any) -> Path | None:
        return coerce_path(value, repo_root=self.current_paths().repo_root)

    def dashboard_snapshot(self) -> dict[str, Any]:
        return get_dashboard_snapshot(paths=self.current_paths())

    def follow_up_agenda(self, *, horizon_days: int = 7) -> dict[str, Any]:
        return get_follow_up_agenda(horizon_days=horizon_days)

    def default_profile_path(self) -> Path:
        return default_web_profile_path(
            default_profile_path=DEFAULT_PROFILE_PATH,
            repo_root=self.current_paths().repo_root,
        )

    def status_choices(self) -> list[str]:
        return tracker_status_choices(repo_root=self.current_paths().repo_root)

    def preset_options(self) -> list[dict[str, str]]:
        return resume_preset_options(
            resume_presets=self.hooks.resume_presets,
            template_presets=self.hooks.template_presets,
        )

    def preset_paths(self, role_key: str, language: str) -> tuple[Path, Path]:
        return resolve_resume_preset(
            role_key,
            language,
            resume_presets=self.hooks.resume_presets,
            template_presets=self.hooks.template_presets,
        )

    def output_path_url(self, path: Path) -> str:
        return output_url(path, paths=self.current_paths())

    def generated_snapshot(self, *, limit: int | None = 6) -> dict[str, Any]:
        return generated_resume_snapshot(paths=self.current_paths(), limit=limit)

    def enriched_generated_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return attach_generated_resume_job_signals(items, paths=self.current_paths())

    def loaded_tailoring_guidance(self, context_path: Path | None) -> dict[str, Any] | None:
        return load_tailoring_guidance(context_path, paths=self.current_paths())

    def live_smoke_status(self, *, max_age_hours: float = 48.0) -> dict[str, Any]:
        return get_live_smoke_status_snapshot(paths=self.current_paths(), max_age_hours=max_age_hours)

    def db_snapshot_dir(self) -> Path:
        return web_db_snapshot_dir(paths=self.current_paths())

    def db_export_path(self) -> Path:
        return new_db_export_path(paths=self.current_paths())

    def attention_snapshot(
        self,
        job_row: dict[str, Any],
        tracker_row: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return job_attention_snapshot(job_row, paths=self.current_paths(), tracker_row=tracker_row)

    def job_ui_state(self, job_row: dict[str, Any]) -> dict[str, Any]:
        return job_row_with_ui_state(job_row, paths=self.current_paths())

    def job_api_payload(self, job_row: Any) -> dict[str, Any]:
        return job_row_api_payload(job_row, paths=self.current_paths())

    def saved_search_state(
        self,
        job_row: dict[str, Any],
        *,
        match_note: str = "canonical URL 기준으로 이미 저장된 항목입니다.",
    ) -> dict[str, Any]:
        return saved_job_search_state(job_row, paths=self.current_paths(), match_note=match_note)

    def enriched_search_results(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return enrich_search_results(items, paths=self.current_paths())

    def search_preset_list(self) -> list[dict[str, Any]]:
        return list_search_presets(connection_scope=connection_scope)

    def search_preset_item(self, preset_key: str) -> dict[str, Any] | None:
        return get_search_preset(preset_key, connection_scope=connection_scope)

    def used_search_preset(self, preset_key: str) -> dict[str, Any] | None:
        return use_search_preset(preset_key, connection_scope=connection_scope)

    def stored_search_preset(self, name: str | None, query: str | None, make_default: bool = False) -> dict[str, Any]:
        return save_search_preset(
            name,
            query,
            connection_scope=connection_scope,
            slugify=slugify,
            make_default=make_default,
        )

    def default_search_preset(self, preset_key: str) -> dict[str, Any]:
        return set_default_search_preset(preset_key, connection_scope=connection_scope)

    def removed_search_preset(self, preset_key: str) -> bool:
        return delete_search_preset(preset_key, connection_scope=connection_scope)

    def artifact_specs(self, job_row: dict[str, Any]) -> list[dict[str, Any]]:
        return job_artifact_specs(job_row, paths=self.current_paths())

    def tracker_row_for_job(self, job_row: dict[str, Any]) -> dict[str, str] | None:
        return load_tracker_row_for_job(job_row, paths=self.current_paths())

    def attached_resume_artifacts(
        self,
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

    def normalized_web_source(self, source: str | None, url: str) -> str | None:
        return normalize_web_source(source, url, safe_text=_safe_text)

    def saved_job_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        paths = self.current_paths()
        return save_job_record(
            payload,
            connection_scope=connection_scope,
            tracker_path=paths.tracker_path,
            normalize_job_url=_normalize_job_url,
            safe_text=_safe_text,
            safe_int=_safe_int,
            safe_bool=_safe_bool,
            upsert_tracker_row=upsert_tracker_row,
            load_tracker_row_for_job=self.tracker_row_for_job,
        )

    def updated_job_record(self, job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        paths = self.current_paths()
        return update_job_record(
            job_id,
            payload,
            connection_scope=connection_scope,
            tracker_path=paths.tracker_path,
            normalize_job_url=_normalize_job_url,
            safe_text=_safe_text,
            safe_int=_safe_int,
            safe_bool=_safe_bool,
            upsert_tracker_row=upsert_tracker_row,
            job_row_api_payload=self.job_api_payload,
        )

    def removed_job_record(self, job_id: int) -> bool:
        paths = self.current_paths()
        return delete_job_record(
            job_id,
            connection_scope=connection_scope,
            tracker_path=paths.tracker_path,
            safe_int=_safe_int,
            delete_tracker_row=delete_tracker_row,
        )

    def bulk_updated_job_records(self, job_ids: list[Any], payload: dict[str, Any]) -> dict[str, Any]:
        return bulk_update_job_records(
            job_ids,
            payload,
            connection_scope=connection_scope,
            safe_int=_safe_int,
            safe_text=_safe_text,
            update_job_record=self.updated_job_record,
        )

    def synced_tracker_rows_to_jobs(self) -> dict[str, int]:
        paths = self.current_paths()
        return sync_tracker_rows_to_jobs(
            tracker_path=paths.tracker_path,
            connection_scope=connection_scope,
            parse_tracker_rows=parse_tracker_rows,
        )

    def search_jobs(self, query: str) -> dict[str, Any]:
        return self.hooks.search_jobs(query)

    def run_build_tailored_resume_from_url(self, *args: Any, **kwargs: Any) -> Any:
        return self.hooks.run_build_tailored_resume_from_url(*args, **kwargs)

    @property
    def list_resumes(self) -> Any:
        return list_resumes

    @property
    def save_uploaded_resume(self) -> Any:
        return save_uploaded_resume

    @property
    def artifact_slug(self) -> Any:
        return artifact_slug

    @property
    def build_focus_preview(self) -> Any:
        return build_focus_preview

    @property
    def filter_generated_resume_items(self) -> Any:
        return filter_generated_resume_items

    @property
    def safe_relative_to(self) -> Any:
        from career_ops_kr.web.common import safe_relative_to as _safe_relative_to

        return _safe_relative_to

    @property
    def describe_save_result(self) -> Any:
        return describe_save_result

    @property
    def job_tracker_sync_snapshot(self) -> Any:
        return job_tracker_sync_snapshot

    @property
    def matches_attention_filter(self) -> Any:
        return matches_attention_filter

    @property
    def resolve_db_path(self) -> Any:
        return resolve_db_path

    @property
    def create_database_backup(self) -> Any:
        return create_database_backup

    @property
    def export_database_snapshot(self) -> Any:
        return export_database_snapshot

    @property
    def import_database_snapshot(self) -> Any:
        return import_database_snapshot

    @property
    def ensure_dir(self) -> Any:
        return ensure_dir

    @property
    def safe_int(self) -> Any:
        return _safe_int

    @property
    def connection_scope(self) -> Any:
        return connection_scope

    @property
    def safe_text(self) -> Any:
        return _safe_text

    @property
    def slugify(self) -> Any:
        return slugify


__all__ = ["WebRouterBindings"]
