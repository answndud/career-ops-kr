from __future__ import annotations

from pathlib import Path

import typer

from career_ops_kr.commands.tracker import run_merge_tracker, run_normalize_statuses, run_verify


def _verify_or_exit() -> None:
    result = run_verify()
    if result.missing:
        typer.echo(f"Missing required files: {', '.join(result.missing)}", err=True)
    if result.duplicates:
        typer.echo(f"Duplicate tracker entries: {', '.join(result.duplicates)}", err=True)
    if result.missing_reports:
        typer.echo(f"Missing report files: {', '.join(result.missing_reports)}", err=True)
    if not result.ok:
        raise typer.Exit(code=1)
    typer.echo("Pipeline verification passed.")


def register_tracker_commands(app: typer.Typer) -> None:
    @app.command("merge-tracker")
    def merge_tracker(
        tracker_path: Path = typer.Option(Path("data/applications.md"), "--tracker-path", help="Applications tracker markdown path."),
        additions_dir: Path = typer.Option(
            Path("data/tracker-additions"),
            "--additions-dir",
            help="Directory containing tracker addition TSV files.",
        ),
        recursive: bool = typer.Option(
            False,
            "--recursive",
            help="Also merge TSV files from subdirectories under --additions-dir.",
        ),
    ) -> None:
        merged = run_merge_tracker(tracker_path, additions_dir, recursive=recursive)
        typer.echo(f"Merged {merged} addition file(s) from {additions_dir.as_posix()}.")

    @app.command("normalize-statuses")
    def normalize_statuses(
        tracker_path: Path = typer.Option(Path("data/applications.md"), "--tracker-path", help="Applications tracker markdown path."),
    ) -> None:
        changed = run_normalize_statuses(tracker_path)
        typer.echo(f"Statuses normalized. Updated {changed} row(s).")

    @app.command("finalize-tracker")
    def finalize_tracker(
        tracker_path: Path = typer.Option(Path("data/applications.md"), "--tracker-path", help="Applications tracker markdown path."),
        additions_dir: Path = typer.Option(
            Path("data/tracker-additions"),
            "--additions-dir",
            help="Directory containing tracker addition TSV files.",
        ),
        recursive: bool = typer.Option(
            True,
            "--recursive/--no-recursive",
            help="Include TSV files from subdirectories when merging additions.",
        ),
        verify_after: bool = typer.Option(
            True,
            "--verify/--no-verify",
            help="Run workspace verification after merge and normalization.",
        ),
    ) -> None:
        merged = run_merge_tracker(tracker_path, additions_dir, recursive=recursive)
        typer.echo(f"Merged {merged} addition file(s) from {additions_dir.as_posix()}.")
        changed = run_normalize_statuses(tracker_path)
        typer.echo(f"Statuses normalized. Updated {changed} row(s).")
        if verify_after:
            _verify_or_exit()
        typer.echo("Tracker finalize complete.")

    @app.command("verify")
    def verify() -> None:
        _verify_or_exit()

