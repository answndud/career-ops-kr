from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from career_ops_kr.portals import canonicalize_job_url, infer_source_from_url
from career_ops_kr.resume_pipeline.live_smoke import (
    DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    list_live_smoke_targets,
    load_live_smoke_target,
)
from career_ops_kr.resume_pipeline.models import (
    BatchLiveResumeSmokeResult,
    BuildTailoredResumeFromUrlArtifacts,
    LiveResumeSmokeArtifacts,
    LiveResumeSmokeCandidate,
    LiveResumeSmokeTarget,
)
from career_ops_kr.utils import slugify


def resume_smoke_run_dir(url: str, source: str) -> Path:
    normalized_url = canonicalize_job_url(url)
    parsed = httpx.URL(normalized_url)
    parts = [part for part in parsed.path.split("/") if part]
    path_hint = "-".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else parsed.host or "job")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = slugify(f"{source}-{path_hint}", fallback="resume-smoke")
    return Path("output") / "live-smoke" / f"{timestamp}-{slug}"


def run_live_resume_smoke_impl(
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
    build_from_url_func: Callable[..., BuildTailoredResumeFromUrlArtifacts],
    load_live_smoke_target_func: Callable[[str, Path], LiveResumeSmokeTarget] = load_live_smoke_target,
    infer_source_func: Callable[[str], str] = infer_source_from_url,
    resume_smoke_run_dir_func: Callable[[str, str], Path] = resume_smoke_run_dir,
) -> LiveResumeSmokeArtifacts:
    selected_target: LiveResumeSmokeTarget | None = None
    if target_key:
        selected_target = load_live_smoke_target_func(target_key, targets_path)

    override_url = url.strip() if url else ""
    target_candidates = selected_target.candidates if selected_target else []
    candidate_pool = (
        [LiveResumeSmokeCandidate(url=override_url, source=source, label="override")]
        if override_url
        else target_candidates
    )
    if not candidate_pool:
        raise ValueError("Live smoke requires a URL or a named target.")

    resolved_base_context = base_context_path or (selected_target.base_context_path if selected_target else None)
    resolved_template = template_path or (selected_target.template_path if selected_target else None)
    resolved_profile = profile_path or (selected_target.profile_path if selected_target else None)
    if resolved_base_context is None:
        raise ValueError("Live smoke requires a base resume context path.")
    if resolved_template is None:
        raise ValueError("Live smoke requires a template path.")
    if resolved_profile is None:
        raise ValueError("Live smoke requires a profile path.")

    failures: list[str] = []
    selected_url = ""
    selected_label: str | None = None
    used_fallback = False
    artifacts: BuildTailoredResumeFromUrlArtifacts | None = None
    run_dir: Path | None = None

    for candidate_index, candidate in enumerate(candidate_pool):
        candidate_url = candidate.url.strip()
        candidate_source = (
            (source or candidate.source or infer_source_func(candidate_url)).strip().lower() or "manual"
        )
        candidate_run_dir = out_dir or resume_smoke_run_dir_func(candidate_url, candidate_source)
        if candidate_run_dir.exists() and not overwrite:
            raise ValueError(
                f"Live smoke output directory already exists: {candidate_run_dir.as_posix()} | Use --overwrite to replace it."
            )
        try:
            artifacts = build_from_url_func(
                candidate_url,
                resolved_base_context,
                resolved_template,
                source=candidate_source,
                job_out=candidate_run_dir / "job.md",
                report_out=candidate_run_dir / "report.md",
                html_out=candidate_run_dir / "resume.html",
                tailoring_out=candidate_run_dir / "tailoring.json",
                tailored_context_out=candidate_run_dir / "context.json",
                pdf_out=(candidate_run_dir / "resume.pdf") if pdf else None,
                profile_path=resolved_profile,
                scorecard_path=scorecard_path,
                overwrite=overwrite,
                insecure=insecure,
                pdf_format=pdf_format,
            )
        except ValueError as exc:
            failures.append(f"{candidate_url} -> {exc}")
            continue

        selected_url = candidate_url
        selected_label = candidate.label
        used_fallback = candidate_index > 0
        run_dir = candidate_run_dir
        break

    if artifacts is None or run_dir is None:
        attempted = "; ".join(failures) if failures else "no candidates attempted"
        raise ValueError(f"Live smoke failed for target '{target_key or 'manual'}': {attempted}")

    required_paths = [
        artifacts.job_path,
        artifacts.report_path,
        artifacts.tailoring_path,
        artifacts.tailored_context_path,
        artifacts.html_path,
    ]
    for path in required_paths:
        if not path.exists():
            raise ValueError(f"Live smoke did not produce expected artifact: {path.as_posix()}")
    if pdf and not artifacts.pdf_path:
        raise ValueError("Live smoke requested PDF output but no PDF artifact was returned.")
    if artifacts.pdf_path and not artifacts.pdf_path.exists():
        raise ValueError(f"Live smoke did not produce expected PDF artifact: {artifacts.pdf_path.as_posix()}")

    cleaned = False
    if not keep_artifacts:
        shutil.rmtree(run_dir, ignore_errors=False)
        cleaned = True

    return LiveResumeSmokeArtifacts(
        run_dir=run_dir,
        job_path=artifacts.job_path,
        report_path=artifacts.report_path,
        tailoring_path=artifacts.tailoring_path,
        tailored_context_path=artifacts.tailored_context_path,
        html_path=artifacts.html_path,
        pdf_path=artifacts.pdf_path,
        selected_url=selected_url,
        candidate_label=selected_label,
        used_fallback=used_fallback,
        cleaned=cleaned,
    )


def run_batch_live_resume_smoke_impl(
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
    run_live_smoke_func: Callable[..., LiveResumeSmokeArtifacts],
    list_live_smoke_targets_func: Callable[[Path], list[LiveResumeSmokeTarget]] = list_live_smoke_targets,
    load_live_smoke_target_func: Callable[[str, Path], LiveResumeSmokeTarget] = load_live_smoke_target,
) -> BatchLiveResumeSmokeResult:
    available_targets = list_live_smoke_targets_func(targets_path)
    selected_keys = target_keys or [target.key for target in available_targets]
    selected_targets = [load_live_smoke_target_func(key, targets_path) for key in selected_keys]

    successes: list[tuple[str, LiveResumeSmokeArtifacts]] = []
    failures: list[tuple[str, str]] = []

    for target in selected_targets:
        try:
            artifacts = run_live_smoke_func(
                target_key=target.key,
                targets_path=targets_path,
                scorecard_path=scorecard_path,
                out_dir=(out_root / target.key) if out_root else None,
                insecure=insecure,
                keep_artifacts=keep_artifacts,
                overwrite=overwrite,
                pdf=pdf,
                pdf_format=pdf_format,
            )
        except ValueError as exc:
            failures.append((target.key, str(exc)))
            if not continue_on_error:
                break
            continue
        successes.append((target.key, artifacts))

    return BatchLiveResumeSmokeResult(successes=successes, failures=failures)


__all__ = [
    "run_batch_live_resume_smoke_impl",
    "run_live_resume_smoke_impl",
]
