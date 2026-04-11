from __future__ import annotations

from pathlib import Path

import httpx
import typer

from career_ops_kr.commands.intake import run_discover_jobs
from career_ops_kr.jobs import fetch_job_to_markdown


def register_intake_fetch_commands(app: typer.Typer) -> None:
    @app.command("fetch-job")
    def fetch_job(
        url: str = typer.Argument(..., help="Target job posting URL."),
        out: Path | None = typer.Option(None, "--out", help="Optional output markdown path."),
        source: str = typer.Option("manual", "--source", help="Source label, e.g. wanted or jumpit."),
        insecure: bool = typer.Option(
            False,
            "--insecure",
            help="Disable TLS certificate verification when local Python CA setup is broken.",
        ),
    ) -> None:
        try:
            output_path = fetch_job_to_markdown(url, out=out, source=source, insecure=insecure)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(output_path.as_posix())

    @app.command("discover-jobs")
    def discover_jobs(
        source: str = typer.Argument(..., help="Portal source: wanted, jumpit, remember, or saramin."),
        limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of job URLs to discover."),
        out: Path = typer.Option(Path("data/pipeline.md"), "--out", help="Pipeline markdown path."),
        insecure: bool = typer.Option(
            False,
            "--insecure",
            help="Disable TLS certificate verification when local Python CA setup is broken.",
        ),
        print_only: bool = typer.Option(
            False,
            "--print-only",
            help="Print discovered URLs instead of updating the pipeline inbox.",
        ),
    ) -> None:
        try:
            result = run_discover_jobs(
                source,
                limit=limit,
                out=out,
                insecure=insecure,
                print_only=print_only,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        except httpx.HTTPError as exc:
            message = f"Failed to discover jobs for {source}: {exc}"
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                message += " | Retry with --insecure if this is a local certificate issue."
            raise typer.BadParameter(message) from exc

        if not result.urls:
            typer.echo(f"No job URLs discovered for {source}.")
            return

        if print_only:
            for url in result.urls:
                typer.echo(url)
            return

        typer.echo(
            f"Discovered {len(result.urls)} URL(s) from {source}. "
            f"Added {result.added} new item(s) to {out.as_posix()}."
        )
