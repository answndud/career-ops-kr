from __future__ import annotations

from pathlib import Path

import typer

from career_ops_kr.commands.intake import (
    DEFAULT_PROFILE_PATH,
    DEFAULT_SCORECARD_PATH,
    run_process_pipeline,
    run_score_job,
)
from career_ops_kr.pipeline import PipelineLockError
from career_ops_kr.scoring import ScoreJobError


def register_intake_pipeline_commands(app: typer.Typer) -> None:
    @app.command("process-pipeline")
    def process_pipeline(
        pipeline_path: Path = typer.Option(Path("data/pipeline.md"), "--pipeline", help="Pipeline markdown path."),
        limit: int = typer.Option(1, "--limit", min=1, help="Maximum number of pending URLs to process."),
        out_dir: Path = typer.Option(Path("jds"), "--out-dir", help="Directory for fetched markdown files."),
        score: bool = typer.Option(
            False,
            "--score",
            help="Also score fetched jobs and create reports plus tracker additions.",
        ),
        report_dir: Path = typer.Option(
            Path("reports"),
            "--report-dir",
            help="Directory for generated reports when --score is set.",
        ),
        tracker_dir: Path = typer.Option(
            Path("data/tracker-additions"),
            "--tracker-dir",
            help="Directory for generated tracker addition TSV files.",
        ),
        profile_path: Path = typer.Option(
            DEFAULT_PROFILE_PATH,
            "--profile-path",
            exists=True,
            readable=True,
            help="Candidate profile YAML used when --score is set.",
        ),
        scorecard_path: Path = typer.Option(
            DEFAULT_SCORECARD_PATH,
            "--scorecard-path",
            exists=True,
            readable=True,
            help="Scorecard YAML used when --score is set.",
        ),
        insecure: bool = typer.Option(
            False,
            "--insecure",
            help="Disable TLS certificate verification when local Python CA setup is broken.",
        ),
    ) -> None:
        try:
            result = run_process_pipeline(
                pipeline_path=pipeline_path,
                limit=limit,
                out_dir=out_dir,
                score=score,
                report_dir=report_dir,
                tracker_dir=tracker_dir,
                profile_path=profile_path,
                scorecard_path=scorecard_path,
                insecure=insecure,
            )
        except PipelineLockError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        if not result.saved_pairs and not result.failures and result.changed == 0:
            typer.echo(f"No pending job URLs in {pipeline_path.as_posix()}.")
            return

        scored_by_path = {job_path: artifacts for job_path, artifacts in result.scored_artifacts}

        for url, output_path in result.saved_pairs:
            typer.echo(f"Saved: {url} -> {output_path.as_posix()}")
            if output_path in scored_by_path:
                artifacts = scored_by_path[output_path]
                typer.echo(
                    "Scored: "
                    f"{output_path.as_posix()} -> {artifacts.report_path.as_posix()} "
                    f"| {artifacts.tracker_path.as_posix()}"
                )

        for failure in result.failures:
            url, _, message = failure.partition(" | ")
            if url in {saved_url for saved_url, _ in result.saved_pairs}:
                typer.echo(f"Failed to score: {url} | {message}", err=True)
            else:
                typer.echo(f"Failed: {url} | {message}", err=True)

        if result.changed:
            typer.echo(f"Marked {result.changed} pipeline item(s) as processed in {pipeline_path.as_posix()}.")

        if result.failures:
            raise typer.Exit(code=1)

    @app.command("score-job")
    def score_job(
        job_path: Path = typer.Argument(..., exists=True, readable=True, help="Markdown job file in jds/."),
        out: Path | None = typer.Option(None, "--out", help="Optional report output path."),
        tracker_out: Path | None = typer.Option(None, "--tracker-out", help="Optional tracker addition TSV path."),
        profile_path: Path = typer.Option(
            DEFAULT_PROFILE_PATH,
            "--profile-path",
            exists=True,
            readable=True,
            help="Candidate profile YAML used for scoring.",
        ),
        scorecard_path: Path = typer.Option(
            DEFAULT_SCORECARD_PATH,
            "--scorecard-path",
            exists=True,
            readable=True,
            help="Scorecard YAML used for scoring.",
        ),
    ) -> None:
        try:
            artifacts = run_score_job(
                job_path,
                report_path=out,
                tracker_path=tracker_out,
                profile_path=profile_path,
                scorecard_path=scorecard_path,
            )
        except ScoreJobError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(f"Report: {artifacts.report_path.as_posix()}")
        typer.echo(f"Tracker addition: {artifacts.tracker_path.as_posix()}")
