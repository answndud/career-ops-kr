from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi.templating import Jinja2Templates

from career_ops_kr.web.router_bindings import WebRouterBindings
from career_ops_kr.web.routers.deps import (
    JobsRouterDeps,
    PagesRouterDeps,
    ResumeRouterDeps,
    SearchRouterDeps,
    SystemRouterDeps,
    WebRouterDeps,
)


@dataclass(frozen=True, slots=True)
class WebRouterFactoryHooks:
    templates: Jinja2Templates
    paths_factory: Callable[[], Any]
    default_web_scorecard_path: Path
    resume_presets: dict[tuple[str, str], Path]
    template_presets: dict[str, Path]
    search_jobs: Callable[[str], dict[str, Any]]
    run_build_tailored_resume_from_url: Callable[..., Any]


def build_router_deps(*, hooks: WebRouterFactoryHooks) -> WebRouterDeps:
    bindings = WebRouterBindings(hooks)
    paths = bindings.current_paths()
    return WebRouterDeps(
        pages=PagesRouterDeps(
            templates=hooks.templates,
            output_dir=paths.output_dir,
            jd_dir=paths.jd_dir,
            report_dir=paths.report_dir,
            connection_scope=bindings.connection_scope,
            resolve_db_path=bindings.resolve_db_path,
            template_context=bindings.template_context,
            get_dashboard_snapshot=bindings.dashboard_snapshot,
            get_follow_up_agenda=bindings.follow_up_agenda,
            get_live_smoke_status_snapshot=bindings.live_smoke_status,
            resume_preset_options=bindings.preset_options,
            generated_resume_snapshot=bindings.generated_snapshot,
            filter_generated_resume_items=bindings.filter_generated_resume_items,
            enrich_generated_resume_items=bindings.enriched_generated_items,
            tracker_status_choices=bindings.status_choices,
            job_row_with_ui_state=bindings.job_ui_state,
            tracker_attention_filters=bindings.tracker_attention_filters,
            tracker_attention_counts=bindings.tracker_attention_counts,
            load_tracker_row_for_job=bindings.tracker_row_for_job,
            load_tailoring_guidance=bindings.loaded_tailoring_guidance,
            coerce_path=bindings.coerce_repo_path,
            job_attention_snapshot=bindings.attention_snapshot,
            job_tracker_sync_snapshot=bindings.job_tracker_sync_snapshot,
            job_artifact_specs=bindings.artifact_specs,
            build_focus_preview=bindings.build_focus_preview,
            safe_relative_to=bindings.safe_relative_to,
            list_resumes=bindings.list_resumes,
            list_search_presets=bindings.search_preset_list,
            get_search_preset=bindings.search_preset_item,
            use_search_preset=bindings.used_search_preset,
            search_jobs=bindings.search_jobs,
            enrich_search_results=bindings.enriched_search_results,
        ),
        jobs=JobsRouterDeps(
            connection_scope=bindings.connection_scope,
            get_follow_up_agenda=bindings.follow_up_agenda,
            job_row_with_ui_state=bindings.job_ui_state,
            save_job_record=bindings.saved_job_record,
            safe_text=bindings.safe_text,
            describe_save_result=bindings.describe_save_result,
            saved_job_search_state=bindings.saved_search_state,
            update_job_record=bindings.updated_job_record,
            bulk_update_job_records=bindings.bulk_updated_job_records,
            delete_job_record=bindings.removed_job_record,
            sync_tracker_rows_to_jobs=bindings.synced_tracker_rows_to_jobs,
            matches_attention_filter=bindings.matches_attention_filter,
        ),
        search=SearchRouterDeps(
            search_jobs=bindings.search_jobs,
            enrich_search_results=bindings.enriched_search_results,
            list_search_presets=bindings.search_preset_list,
            save_search_preset=bindings.stored_search_preset,
            set_default_search_preset=bindings.default_search_preset,
            delete_search_preset=bindings.removed_search_preset,
        ),
        resume=ResumeRouterDeps(
            output_dir=paths.output_dir,
            jd_dir=paths.jd_dir,
            report_dir=paths.report_dir,
            web_resume_output_dir=paths.web_resume_output_dir,
            default_web_scorecard_path=hooks.default_web_scorecard_path,
            resume_preset_options=bindings.preset_options,
            default_web_profile_path=bindings.default_profile_path,
            list_resumes=bindings.list_resumes,
            save_uploaded_resume=bindings.save_uploaded_resume,
            normalize_web_source=bindings.normalized_web_source,
            resolve_resume_preset=bindings.preset_paths,
            artifact_slug=bindings.artifact_slug,
            run_build_tailored_resume_from_url=bindings.run_build_tailored_resume_from_url,
            attach_resume_artifacts_to_job=bindings.attached_resume_artifacts,
            safe_int=bindings.safe_int,
            output_url=bindings.output_path_url,
            load_tailoring_guidance=bindings.loaded_tailoring_guidance,
            ensure_dir=bindings.ensure_dir,
        ),
        system=SystemRouterDeps(
            resolve_db_path=bindings.resolve_db_path,
            get_dashboard_snapshot=bindings.dashboard_snapshot,
            get_live_smoke_status_snapshot=bindings.live_smoke_status,
            create_database_backup=bindings.create_database_backup,
            export_database_snapshot=bindings.export_database_snapshot,
            import_database_snapshot=bindings.import_database_snapshot,
            ensure_dir=bindings.ensure_dir,
            web_db_snapshot_dir=bindings.db_snapshot_dir,
            new_db_export_path=bindings.db_export_path,
            slugify=bindings.slugify,
        ),
    )


__all__ = ["WebRouterFactoryHooks", "build_router_deps"]
