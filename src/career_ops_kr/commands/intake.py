from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from career_ops_kr.jobs import fetch_job_to_markdown
from career_ops_kr.pipeline import acquire_pipeline_lock, list_pending_urls, mark_urls_processed
from career_ops_kr.portals import discover_job_urls, infer_source_from_url, merge_pending_urls
from career_ops_kr.scoring import ScoreJobArtifacts, score_job_file


DEFAULT_PROFILE_PATH = Path("config/profile.yml")
DEFAULT_SCORECARD_PATH = Path("config/scorecard.kr.yml")


@dataclass(slots=True)
class DiscoverJobsResult:
    urls: list[str]
    added: int


@dataclass(slots=True)
class ProcessPipelineResult:
    saved_pairs: list[tuple[str, Path]]
    scored_artifacts: list[tuple[Path, ScoreJobArtifacts]]
    failures: list[str]
    changed: int


def run_discover_jobs(
    source: str,
    *,
    limit: int,
    out: Path,
    insecure: bool,
    print_only: bool,
) -> DiscoverJobsResult:
    urls = discover_job_urls(source, limit=limit, insecure=insecure)
    if print_only or not urls:
        return DiscoverJobsResult(urls=urls, added=0)
    return DiscoverJobsResult(urls=urls, added=merge_pending_urls(out, urls))


def run_process_pipeline(
    *,
    pipeline_path: Path,
    limit: int,
    out_dir: Path,
    score: bool,
    report_dir: Path,
    tracker_dir: Path,
    profile_path: Path,
    scorecard_path: Path,
    insecure: bool,
    fetch_job_func: Callable[..., Path] | None = None,
    infer_source_func: Callable[[str], str] | None = None,
    score_job_func: Callable[..., ScoreJobArtifacts] | None = None,
) -> ProcessPipelineResult:
    fetch_job = fetch_job_func or fetch_job_to_markdown
    infer_source = infer_source_func or infer_source_from_url
    score_job = score_job_func or score_job_file

    with acquire_pipeline_lock(pipeline_path):
        pending_urls = list_pending_urls(pipeline_path)
        selected_urls = pending_urls[:limit]
        if not selected_urls:
            return ProcessPipelineResult(saved_pairs=[], scored_artifacts=[], failures=[], changed=0)

        saved_pairs: list[tuple[str, Path]] = []
        scored_artifacts: list[tuple[Path, ScoreJobArtifacts]] = []
        failures: list[str] = []

        for url in selected_urls:
            source = infer_source(url)
            try:
                output_path = fetch_job(
                    url,
                    output_dir=out_dir,
                    source=source,
                    insecure=insecure,
                )
            except ValueError as exc:
                failures.append(f"{url} | {exc}")
                continue

            saved_pairs.append((url, output_path))

            if not score:
                continue

            try:
                artifacts = score_job(
                    output_path,
                    report_dir=report_dir,
                    tracker_dir=tracker_dir,
                    profile_path=profile_path,
                    scorecard_path=scorecard_path,
                )
            except ValueError as exc:
                failures.append(f"{url} | {exc}")
                continue

            scored_artifacts.append((output_path, artifacts))

        changed = mark_urls_processed(pipeline_path, [url for url, _ in saved_pairs])
        return ProcessPipelineResult(
            saved_pairs=saved_pairs,
            scored_artifacts=scored_artifacts,
            failures=failures,
            changed=changed,
        )


def run_score_job(
    job_path: Path,
    *,
    report_path: Path | None = None,
    tracker_path: Path | None = None,
    profile_path: Path = DEFAULT_PROFILE_PATH,
    scorecard_path: Path = DEFAULT_SCORECARD_PATH,
) -> ScoreJobArtifacts:
    return score_job_file(
        job_path,
        report_path=report_path,
        tracker_path=tracker_path,
        profile_path=profile_path,
        scorecard_path=scorecard_path,
    )
