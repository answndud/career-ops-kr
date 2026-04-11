from __future__ import annotations

from pathlib import Path

import typer

from career_ops_kr.commands.research import (
    COMPANY_RESEARCH_PROMPT_PATH,
    run_prepare_company_followup,
    run_prepare_company_research,
)


def register_research_commands(app: typer.Typer) -> None:
    @app.command("prepare-company-research")
    def prepare_company_research(
        company_name: str = typer.Argument(..., help="Target company name."),
        out: Path | None = typer.Option(None, "--out", help="Optional research brief output path."),
        homepage: str | None = typer.Option(None, "--homepage", help="Official homepage URL."),
        careers_url: str | None = typer.Option(None, "--careers-url", help="Official careers page URL."),
        job_url: str | None = typer.Option(None, "--job-url", help="Target job posting URL for this brief."),
        jobplanet_url: str | None = typer.Option(None, "--jobplanet-url", help="Known JobPlanet company URL."),
        blind_url: str | None = typer.Option(None, "--blind-url", help="Known Blind company URL."),
        job_path: Path | None = typer.Option(None, "--job-path", help="Optional saved JD markdown path."),
        report_path: Path | None = typer.Option(None, "--report-path", help="Optional score report path."),
        extra_source: list[str] = typer.Option(
            None,
            "--extra-source",
            help="Additional source in LABEL=URL format. Repeatable.",
        ),
        prompt_path: Path = typer.Option(
            COMPANY_RESEARCH_PROMPT_PATH,
            "--prompt-path",
            exists=True,
            readable=True,
            help="Prompt template used to seed the research checklist.",
        ),
        overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing research brief file."),
    ) -> None:
        try:
            output_path = run_prepare_company_research(
                company_name,
                out=out,
                homepage=homepage,
                careers_url=careers_url,
                job_url=job_url,
                jobplanet_url=jobplanet_url,
                blind_url=blind_url,
                job_path=job_path,
                report_path=report_path,
                extra_sources=extra_source or [],
                prompt_path=prompt_path,
                overwrite=overwrite,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(output_path.as_posix())

    @app.command("prepare-company-followup")
    def prepare_company_followup(
        research_path: Path = typer.Argument(..., exists=True, readable=True, help="Existing research brief markdown path."),
        mode: str = typer.Option("summary", "--mode", help="Follow-up mode: summary or outreach."),
        out: Path | None = typer.Option(None, "--out", help="Optional follow-up output markdown path."),
        overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing follow-up file."),
    ) -> None:
        try:
            output_path = run_prepare_company_followup(
                research_path,
                mode=mode.strip().lower(),
                out=out,
                overwrite=overwrite,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(output_path.as_posix())

