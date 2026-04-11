from __future__ import annotations

import json
from pathlib import Path

import typer

from career_ops_kr.commands.tracker import run_audit_jobs, run_merge_tracker, run_normalize_statuses, run_verify


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
    @app.command("audit-jobs")
    def audit_jobs(
        tracker_path: Path = typer.Option(Path("data/applications.md"), "--tracker-path", help="Applications tracker markdown path."),
        repo_root: Path = typer.Option(Path("."), "--repo-root", help="Repository root used to resolve relative tracker artifact paths."),
        output_dir: Path = typer.Option(
            Path("output"),
            "--output-dir",
            help="Output root to scan for manifest/index drift and legacy HTML artifacts.",
        ),
        limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of findings to print in text mode."),
        as_json: bool = typer.Option(False, "--json", help="Print the audit result as JSON."),
        strict: bool = typer.Option(False, "--strict", help="Exit with code 1 when any findings are present."),
    ) -> None:
        result = run_audit_jobs(
            tracker_path,
            repo_root=repo_root,
            output_dir=output_dir,
        )
        if as_json:
            typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            typer.echo(f"Tracker rows: {result.tracker_row_count}")
            typer.echo(f"Findings: {len(result.findings)}")
            if result.findings:
                typer.echo("Counts:")
                for category, count in result.counts.items():
                    typer.echo(f"- {category}: {count}")
                typer.echo("Details:")
                for finding in result.findings[:limit]:
                    subject = ""
                    if finding.tracker_id:
                        subject = f"[{finding.tracker_id}] {finding.company} / {finding.role}: "
                    path_suffix = f" ({finding.path})" if finding.path else ""
                    typer.echo(f"- {finding.category}: {subject}{finding.message}{path_suffix}")
                remaining = len(result.findings) - limit
                if remaining > 0:
                    typer.echo(f"... {remaining} more finding(s)")
            else:
                typer.echo("No audit findings.")
        if strict and not result.ok:
            raise typer.Exit(code=1)

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
