from __future__ import annotations

from pathlib import Path
from typing import Any

from career_ops_kr.jobs import fetch_job_to_markdown
from career_ops_kr.portals import infer_source_from_url
from career_ops_kr.resume_pipeline.artifacts import (
    ARTIFACT_INDEX_FILENAME,
    _default_resume_artifact_manifest_path,
    _new_build_run_id,
    _write_resume_artifact_manifest,
    backfill_artifact_manifests,
    load_resume_artifact_manifest,
)
from career_ops_kr.resume_pipeline.live_smoke import (
    DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    compare_live_smoke_reports,
    describe_live_smoke_report_filters,
    evaluate_live_smoke_report_health,
    get_live_smoke_report_scan_summary,
    list_latest_live_smoke_entries_by_target,
    list_live_smoke_reports,
    list_live_smoke_targets,
    live_smoke_report_metadata,
    load_live_smoke_target,
    resolve_latest_live_smoke_report,
    resolve_latest_live_smoke_report_pair,
    summarize_ignored_live_smoke_reports,
    summarize_live_smoke_report,
    write_live_smoke_batch_report,
    write_live_smoke_report,
)
from career_ops_kr.resume_pipeline.models import (
    BackfillArtifactManifestResult,
    BatchLiveResumeSmokeResult,
    BuildTailoredResumeArtifacts,
    BuildTailoredResumeFromUrlArtifacts,
    LiveResumeSmokeArtifacts,
    LiveResumeSmokeCandidate,
    LiveResumeSmokeTarget,
    LiveSmokeReportHealthEntry,
    ResumeTailoringArtifacts,
    TailoredResumeContextArtifacts,
)
from career_ops_kr.resume_pipeline.build import (
    build_tailored_resume_from_url_impl,
    build_tailored_resume_impl,
)
from career_ops_kr.resume_pipeline.rendering import generate_pdf_file, render_resume_html
from career_ops_kr.resume_pipeline.smoke_runner import (
    run_batch_live_resume_smoke_impl,
    run_live_resume_smoke_impl,
)
from career_ops_kr.resume_pipeline.tailoring import (
    apply_resume_tailoring_packet,
    create_resume_tailoring_packet,
)
from career_ops_kr.scoring import score_job_file


REPO_ROOT = Path(__file__).resolve().parents[3]


def build_tailored_resume(
    job_path: Path,
    report_path: Path,
    base_context_path: Path,
    template_path: Path,
    *,
    html_out: Path | None = None,
    tailoring_out: Path | None = None,
    tailored_context_out: Path | None = None,
    pdf_out: Path | None = None,
    scorecard_path: Path = REPO_ROOT / "config" / "scorecard.kr.yml",
    overwrite: bool = False,
    pdf_format: str = "A4",
    build_run_id: str | None = None,
) -> BuildTailoredResumeArtifacts:
    return build_tailored_resume_impl(
        job_path,
        report_path,
        base_context_path,
        template_path,
        html_out=html_out,
        tailoring_out=tailoring_out,
        tailored_context_out=tailored_context_out,
        pdf_out=pdf_out,
        scorecard_path=scorecard_path,
        overwrite=overwrite,
        pdf_format=pdf_format,
        build_run_id=build_run_id,
        create_resume_tailoring_packet_func=create_resume_tailoring_packet,
        apply_resume_tailoring_packet_func=apply_resume_tailoring_packet,
        render_resume_html_func=render_resume_html,
        generate_pdf_file_func=generate_pdf_file,
        default_resume_artifact_manifest_path_func=_default_resume_artifact_manifest_path,
        new_build_run_id_func=_new_build_run_id,
        write_resume_artifact_manifest_func=_write_resume_artifact_manifest,
    )


def build_tailored_resume_from_url(
    url: str,
    base_context_path: Path,
    template_path: Path,
    *,
    source: str | None = None,
    job_out: Path | None = None,
    report_out: Path | None = None,
    tracker_out: Path | None = None,
    html_out: Path | None = None,
    tailoring_out: Path | None = None,
    tailored_context_out: Path | None = None,
    pdf_out: Path | None = None,
    profile_path: Path = REPO_ROOT / "config" / "profile.yml",
    scorecard_path: Path = REPO_ROOT / "config" / "scorecard.kr.yml",
    overwrite: bool = False,
    insecure: bool = False,
    pdf_format: str = "A4",
    fetch_job_func: Any | None = None,
    score_job_func: Any | None = None,
    build_tailored_resume_func: Any | None = None,
    infer_source_func: Any | None = None,
) -> BuildTailoredResumeFromUrlArtifacts:
    return build_tailored_resume_from_url_impl(
        url,
        base_context_path,
        template_path,
        source=source,
        job_out=job_out,
        report_out=report_out,
        tracker_out=tracker_out,
        html_out=html_out,
        tailoring_out=tailoring_out,
        tailored_context_out=tailored_context_out,
        pdf_out=pdf_out,
        profile_path=profile_path,
        scorecard_path=scorecard_path,
        overwrite=overwrite,
        insecure=insecure,
        pdf_format=pdf_format,
        fetch_job_func=fetch_job_func or fetch_job_to_markdown,
        score_job_func=score_job_func or score_job_file,
        build_tailored_resume_func=build_tailored_resume_func or build_tailored_resume,
        infer_source_func=infer_source_func or infer_source_from_url,
        default_resume_artifact_manifest_path_func=_default_resume_artifact_manifest_path,
        new_build_run_id_func=_new_build_run_id,
        write_resume_artifact_manifest_func=_write_resume_artifact_manifest,
    )


def run_live_resume_smoke(
    *,
    url: str | None = None,
    base_context_path: Path | None = None,
    template_path: Path | None = None,
    profile_path: Path | None = None,
    scorecard_path: Path,
    source: str | None = None,
    target_key: str | None = None,
    targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    out_dir: Path | None = None,
    insecure: bool = False,
    keep_artifacts: bool = False,
    overwrite: bool = False,
    pdf: bool = False,
    pdf_format: str = "A4",
    build_from_url_func: Any | None = None,
) -> LiveResumeSmokeArtifacts:
    return run_live_resume_smoke_impl(
        url=url,
        base_context_path=base_context_path,
        template_path=template_path,
        profile_path=profile_path,
        scorecard_path=scorecard_path,
        source=source,
        target_key=target_key,
        targets_path=targets_path,
        out_dir=out_dir,
        insecure=insecure,
        keep_artifacts=keep_artifacts,
        overwrite=overwrite,
        pdf=pdf,
        pdf_format=pdf_format,
        build_from_url_func=build_from_url_func or build_tailored_resume_from_url,
        load_live_smoke_target_func=load_live_smoke_target,
        infer_source_func=infer_source_from_url,
    )


def run_batch_live_resume_smoke(
    *,
    target_keys: list[str] | None,
    targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    scorecard_path: Path,
    out_root: Path | None = None,
    insecure: bool = False,
    keep_artifacts: bool = False,
    overwrite: bool = False,
    pdf: bool = False,
    pdf_format: str = "A4",
    continue_on_error: bool = True,
    run_live_smoke_func: Any | None = None,
) -> BatchLiveResumeSmokeResult:
    return run_batch_live_resume_smoke_impl(
        target_keys=target_keys,
        targets_path=targets_path,
        scorecard_path=scorecard_path,
        out_root=out_root,
        insecure=insecure,
        keep_artifacts=keep_artifacts,
        overwrite=overwrite,
        pdf=pdf,
        pdf_format=pdf_format,
        continue_on_error=continue_on_error,
        run_live_smoke_func=run_live_smoke_func or run_live_resume_smoke,
        list_live_smoke_targets_func=list_live_smoke_targets,
        load_live_smoke_target_func=load_live_smoke_target,
    )
