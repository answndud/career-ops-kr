from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from career_ops_kr.portals import canonicalize_job_url, infer_source_from_url
from career_ops_kr.resume_pipeline.models import (
    BuildTailoredResumeArtifacts,
    BuildTailoredResumeFromUrlArtifacts,
)
from career_ops_kr.scoring import ScoreJobArtifacts, score_job_file
from career_ops_kr.utils import parse_front_matter, slugify, title_case


REPO_ROOT = Path(__file__).resolve().parents[3]


def resume_artifact_slug(job_path: Path) -> tuple[str, str]:
    metadata, _body = parse_front_matter(job_path)
    company = title_case(str(metadata.get("company") or "Unknown"))
    title = title_case(str(metadata.get("title") or job_path.stem))
    return datetime.now(UTC).date().isoformat(), slugify(f"{company}-{title}", fallback="resume")


def resume_url_artifact_slug(url: str, source: str) -> tuple[str, str]:
    normalized_url = canonicalize_job_url(url)
    parsed = httpx.URL(normalized_url)
    parts = [part for part in parsed.path.split("/") if part]
    path_hint = "-".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else parsed.host or "job")
    return datetime.now(UTC).date().isoformat(), slugify(f"{source}-{path_hint}", fallback="resume")


def build_tailored_resume_impl(
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
    create_resume_tailoring_packet_func: Callable[..., Any],
    apply_resume_tailoring_packet_func: Callable[..., Any],
    render_resume_html_func: Callable[[Path, Path, Path], Path],
    generate_pdf_file_func: Callable[[Path, Path, str], Path],
    default_resume_artifact_manifest_path_func: Callable[[Path], Path],
    new_build_run_id_func: Callable[[], str],
    write_resume_artifact_manifest_func: Callable[..., Path],
) -> BuildTailoredResumeArtifacts:
    if not job_path.exists():
        raise ValueError(f"Job markdown path does not exist: {job_path.as_posix()}")
    if not report_path.exists():
        raise ValueError(f"Score report path does not exist: {report_path.as_posix()}")
    if not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")
    if not template_path.exists():
        raise ValueError(f"Resume template does not exist: {template_path.as_posix()}")

    date, slug = resume_artifact_slug(job_path)
    resolved_tailoring_out = tailoring_out or Path("output") / "resume-tailoring" / f"{date}-{slug}.json"
    resolved_context_out = tailored_context_out or Path("output") / "resume-contexts" / f"{date}-{slug}.json"
    resolved_html_out = html_out or Path("output") / "rendered-resumes" / f"{date}-{slug}.html"
    resolved_manifest_out = default_resume_artifact_manifest_path_func(resolved_html_out)
    resolved_build_run_id = build_run_id or new_build_run_id_func()

    protected_outputs = [
        resolved_tailoring_out,
        resolved_context_out,
        resolved_html_out,
        resolved_manifest_out,
    ]
    if pdf_out:
        protected_outputs.append(pdf_out)
    existing_outputs = [path for path in protected_outputs if path.exists()]
    if existing_outputs and not overwrite:
        joined = ", ".join(path.as_posix() for path in existing_outputs)
        raise ValueError(f"Resume build output already exists: {joined} | Use --overwrite to replace it.")

    tailoring = create_resume_tailoring_packet_func(
        job_path,
        report_path,
        out=resolved_tailoring_out,
        base_context_path=base_context_path,
        scorecard_path=scorecard_path,
        overwrite=overwrite,
    )
    tailored_context = apply_resume_tailoring_packet_func(
        tailoring.output_path,
        base_context_path,
        out=resolved_context_out,
        overwrite=overwrite,
    )
    render_resume_html_func(template_path, tailored_context.output_path, resolved_html_out)

    resolved_pdf_out: Path | None = None
    if pdf_out:
        resolved_pdf_out = generate_pdf_file_func(resolved_html_out, pdf_out, pdf_format)
    manifest_path = write_resume_artifact_manifest_func(
        manifest_path=resolved_manifest_out,
        pipeline="build_tailored_resume",
        job_path=job_path,
        report_path=report_path,
        tailoring_path=tailoring.output_path,
        context_path=tailored_context.output_path,
        html_path=resolved_html_out,
        pdf_path=resolved_pdf_out,
        base_context_path=base_context_path,
        template_path=template_path,
        scorecard_path=scorecard_path,
        build_run_id=resolved_build_run_id,
    )

    return BuildTailoredResumeArtifacts(
        tailoring_path=tailoring.output_path,
        tailored_context_path=tailored_context.output_path,
        html_path=resolved_html_out,
        pdf_path=resolved_pdf_out,
        manifest_path=manifest_path,
    )


def build_tailored_resume_from_url_impl(
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
    fetch_job_func: Callable[..., Path],
    score_job_func: Callable[..., ScoreJobArtifacts] = score_job_file,
    build_tailored_resume_func: Callable[..., BuildTailoredResumeArtifacts],
    infer_source_func: Callable[[str], str] = infer_source_from_url,
    default_resume_artifact_manifest_path_func: Callable[[Path], Path],
    new_build_run_id_func: Callable[[], str],
    write_resume_artifact_manifest_func: Callable[..., Path],
) -> BuildTailoredResumeFromUrlArtifacts:
    if not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")
    if not template_path.exists():
        raise ValueError(f"Resume template does not exist: {template_path.as_posix()}")
    if not profile_path.exists():
        raise ValueError(f"Profile path does not exist: {profile_path.as_posix()}")
    if not scorecard_path.exists():
        raise ValueError(f"Scorecard path does not exist: {scorecard_path.as_posix()}")

    resolved_source = (source or infer_source_func(url)).strip().lower() or "manual"
    date, slug = resume_url_artifact_slug(url, resolved_source)
    resolved_job_out = job_out or Path("jds") / f"{date}-{slug}.md"
    resolved_report_out = report_out or Path("reports") / f"{date}-{slug}.md"
    resolved_tailoring_out = tailoring_out or Path("output") / "resume-tailoring" / f"{date}-{slug}.json"
    resolved_context_out = tailored_context_out or Path("output") / "resume-contexts" / f"{date}-{slug}.json"
    resolved_html_out = html_out or Path("output") / "rendered-resumes" / f"{date}-{slug}.html"
    resolved_manifest_out = default_resume_artifact_manifest_path_func(resolved_html_out)
    resolved_build_run_id = new_build_run_id_func()

    protected_outputs = [
        resolved_job_out,
        resolved_report_out,
        resolved_tailoring_out,
        resolved_context_out,
        resolved_html_out,
        resolved_manifest_out,
    ]
    if tracker_out:
        protected_outputs.append(tracker_out)
    if pdf_out:
        protected_outputs.append(pdf_out)
    existing_outputs = [path for path in protected_outputs if path.exists()]
    if existing_outputs and not overwrite:
        joined = ", ".join(path.as_posix() for path in existing_outputs)
        raise ValueError(
            f"Resume-from-url output already exists: {joined} | Use --overwrite to replace it."
        )

    saved_job_path = fetch_job_func(
        url,
        out=resolved_job_out,
        source=resolved_source,
        insecure=insecure,
    )
    score_artifacts = score_job_func(
        saved_job_path,
        report_path=resolved_report_out,
        tracker_path=tracker_out,
        profile_path=profile_path,
        scorecard_path=scorecard_path,
        write_tracker=tracker_out is not None,
    )
    resume_artifacts = build_tailored_resume_func(
        saved_job_path,
        score_artifacts.report_path,
        base_context_path,
        template_path,
        html_out=resolved_html_out,
        tailoring_out=resolved_tailoring_out,
        tailored_context_out=resolved_context_out,
        pdf_out=pdf_out,
        scorecard_path=scorecard_path,
        overwrite=overwrite,
        pdf_format=pdf_format,
        build_run_id=resolved_build_run_id,
    )
    manifest_path = write_resume_artifact_manifest_func(
        manifest_path=resume_artifacts.manifest_path
        or default_resume_artifact_manifest_path_func(resume_artifacts.html_path),
        pipeline="build_tailored_resume_from_url",
        job_path=saved_job_path,
        report_path=score_artifacts.report_path,
        tailoring_path=resume_artifacts.tailoring_path,
        context_path=resume_artifacts.tailored_context_path,
        html_path=resume_artifacts.html_path,
        pdf_path=resume_artifacts.pdf_path,
        base_context_path=base_context_path,
        template_path=template_path,
        scorecard_path=scorecard_path,
        profile_path=profile_path,
        build_run_id=resolved_build_run_id,
    )

    return BuildTailoredResumeFromUrlArtifacts(
        job_path=saved_job_path,
        report_path=score_artifacts.report_path,
        tracker_path=score_artifacts.tracker_path,
        tailoring_path=resume_artifacts.tailoring_path,
        tailored_context_path=resume_artifacts.tailored_context_path,
        html_path=resume_artifacts.html_path,
        pdf_path=resume_artifacts.pdf_path,
        manifest_path=manifest_path,
    )


__all__ = [
    "build_tailored_resume_impl",
    "build_tailored_resume_from_url_impl",
]

