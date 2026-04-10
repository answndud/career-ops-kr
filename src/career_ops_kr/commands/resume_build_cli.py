from __future__ import annotations

from pathlib import Path

import typer

from career_ops_kr.commands.intake import DEFAULT_PROFILE_PATH, DEFAULT_SCORECARD_PATH
from career_ops_kr.commands.resume import (
    apply_resume_tailoring_packet,
    backfill_artifact_manifests,
    build_tailored_resume,
    build_tailored_resume_from_url,
    create_resume_tailoring_packet,
    generate_pdf_file,
    render_resume_html,
)


def register_resume_build_commands(app: typer.Typer) -> None:
    @app.command("render-resume")
    def render_resume(
        template_path: Path = typer.Argument(..., exists=True, readable=True),
        context_path: Path = typer.Argument(..., exists=True, readable=True),
        output_path: Path = typer.Argument(...),
    ) -> None:
        typer.echo(render_resume_html(template_path, context_path, output_path).as_posix())

    @app.command("prepare-resume-tailoring")
    def prepare_resume_tailoring(
        job_path: Path = typer.Argument(..., exists=True, readable=True, help="Saved JD markdown path."),
        report_path: Path = typer.Argument(..., exists=True, readable=True, help="Existing score report markdown path."),
        out: Path | None = typer.Option(None, "--out", help="Optional resume-tailoring JSON output path."),
        base_context: Path | None = typer.Option(
            None,
            "--base-context",
            exists=True,
            readable=True,
            help="Optional base resume context JSON used to mark matched and missing skills.",
        ),
        scorecard_path: Path = typer.Option(
            DEFAULT_SCORECARD_PATH,
            "--scorecard-path",
            exists=True,
            readable=True,
            help="Scorecard YAML used to resolve role-profile keyword hints.",
        ),
        overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing tailoring packet."),
    ) -> None:
        try:
            artifacts = create_resume_tailoring_packet(
                job_path,
                report_path,
                out=out,
                base_context_path=base_context,
                scorecard_path=scorecard_path,
                overwrite=overwrite,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(artifacts.output_path.as_posix())

    @app.command("build-tailored-resume")
    def build_tailored_resume_command(
        job_path: Path = typer.Argument(..., exists=True, readable=True, help="Saved JD markdown path."),
        report_path: Path = typer.Argument(..., exists=True, readable=True, help="Existing score report markdown path."),
        base_context_path: Path = typer.Argument(..., exists=True, readable=True, help="Base resume context JSON path."),
        template_path: Path = typer.Argument(..., exists=True, readable=True, help="Resume template HTML path."),
        html_out: Path | None = typer.Option(None, "--html-out", help="Optional rendered resume HTML output path."),
        tailoring_out: Path | None = typer.Option(
            None,
            "--tailoring-out",
            help="Optional intermediate resume-tailoring JSON output path.",
        ),
        context_out: Path | None = typer.Option(
            None,
            "--context-out",
            help="Optional tailored resume context JSON output path.",
        ),
        pdf_out: Path | None = typer.Option(None, "--pdf-out", help="Optional PDF output path."),
        pdf_format: str = typer.Option("A4", "--pdf-format", help="Playwright PDF page format when --pdf-out is set."),
        scorecard_path: Path = typer.Option(
            DEFAULT_SCORECARD_PATH,
            "--scorecard-path",
            exists=True,
            readable=True,
            help="Scorecard YAML used to resolve role-profile keyword hints.",
        ),
        overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing wrapper outputs."),
    ) -> None:
        try:
            artifacts = build_tailored_resume(
                job_path,
                report_path,
                base_context_path,
                template_path,
                html_out=html_out,
                tailoring_out=tailoring_out,
                tailored_context_out=context_out,
                pdf_out=pdf_out,
                scorecard_path=scorecard_path,
                overwrite=overwrite,
                pdf_format=pdf_format,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(f"Tailoring: {artifacts.tailoring_path.as_posix()}")
        typer.echo(f"Tailored context: {artifacts.tailored_context_path.as_posix()}")
        typer.echo(f"HTML: {artifacts.html_path.as_posix()}")
        if artifacts.pdf_path:
            typer.echo(f"PDF: {artifacts.pdf_path.as_posix()}")
        if artifacts.manifest_path:
            typer.echo(f"Manifest: {artifacts.manifest_path.as_posix()}")

    @app.command("build-tailored-resume-from-url")
    def build_tailored_resume_from_url_command(
        url: str = typer.Argument(..., help="Target job posting URL."),
        base_context_path: Path = typer.Argument(..., exists=True, readable=True, help="Base resume context JSON path."),
        template_path: Path = typer.Argument(..., exists=True, readable=True, help="Resume template HTML path."),
        source: str | None = typer.Option(None, "--source", help="Optional source override. Defaults to URL-based inference."),
        job_out: Path | None = typer.Option(None, "--job-out", help="Optional fetched JD markdown output path."),
        report_out: Path | None = typer.Option(None, "--report-out", help="Optional score report markdown output path."),
        tracker_out: Path | None = typer.Option(
            None,
            "--tracker-out",
            help="Optional tracker addition TSV output path. Omit to avoid tracker side effects.",
        ),
        html_out: Path | None = typer.Option(None, "--html-out", help="Optional rendered resume HTML output path."),
        tailoring_out: Path | None = typer.Option(
            None,
            "--tailoring-out",
            help="Optional intermediate resume-tailoring JSON output path.",
        ),
        context_out: Path | None = typer.Option(
            None,
            "--context-out",
            help="Optional tailored resume context JSON output path.",
        ),
        pdf_out: Path | None = typer.Option(None, "--pdf-out", help="Optional PDF output path."),
        pdf_format: str = typer.Option("A4", "--pdf-format", help="Playwright PDF page format when --pdf-out is set."),
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
            help="Scorecard YAML used for scoring and resume keyword hints.",
        ),
        insecure: bool = typer.Option(
            False,
            "--insecure",
            help="Disable TLS certificate verification when local Python CA setup is broken.",
        ),
        overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing wrapper outputs."),
    ) -> None:
        try:
            artifacts = build_tailored_resume_from_url(
                url,
                base_context_path,
                template_path,
                source=source,
                job_out=job_out,
                report_out=report_out,
                tracker_out=tracker_out,
                html_out=html_out,
                tailoring_out=tailoring_out,
                tailored_context_out=context_out,
                pdf_out=pdf_out,
                profile_path=profile_path,
                scorecard_path=scorecard_path,
                overwrite=overwrite,
                insecure=insecure,
                pdf_format=pdf_format,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(f"Job: {artifacts.job_path.as_posix()}")
        typer.echo(f"Report: {artifacts.report_path.as_posix()}")
        if artifacts.tracker_path:
            typer.echo(f"Tracker addition: {artifacts.tracker_path.as_posix()}")
        typer.echo(f"Tailoring: {artifacts.tailoring_path.as_posix()}")
        typer.echo(f"Tailored context: {artifacts.tailored_context_path.as_posix()}")
        typer.echo(f"HTML: {artifacts.html_path.as_posix()}")
        if artifacts.pdf_path:
            typer.echo(f"PDF: {artifacts.pdf_path.as_posix()}")
        if artifacts.manifest_path:
            typer.echo(f"Manifest: {artifacts.manifest_path.as_posix()}")

    @app.command("backfill-artifact-manifests")
    def backfill_artifact_manifests_command(
        output_dir: Path = typer.Option(Path("output"), "--output-dir", help="Root output directory to scan for HTML artifacts."),
        jd_dir: Path = typer.Option(Path("jds"), "--jd-dir", help="JD markdown directory used for legacy path inference."),
        report_dir: Path = typer.Option(
            Path("reports"),
            "--report-dir",
            help="Score report directory used for legacy path inference.",
        ),
        overwrite: bool = typer.Option(
            False,
            "--overwrite",
            help="Rewrite existing sibling manifest files instead of skipping them.",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="List which manifest files would be written without modifying disk.",
        ),
    ) -> None:
        result = backfill_artifact_manifests(
            output_dir=output_dir,
            jd_dir=jd_dir,
            report_dir=report_dir,
            overwrite=overwrite,
            dry_run=dry_run,
        )
        typer.echo(f"Scanned HTML artifacts: {result.scanned}")
        typer.echo(f"Created: {result.created}")
        typer.echo(f"Overwritten: {result.overwritten}")
        typer.echo(f"Skipped: {result.skipped}")
        if result.manifests:
            typer.echo("Manifest paths:")
            for path in result.manifests:
                typer.echo(path.as_posix())

    @app.command("generate-pdf")
    def generate_pdf(
        input_path: Path = typer.Argument(..., exists=True, readable=True),
        output_path: Path = typer.Argument(...),
        page_format: str = typer.Option("A4", "--format", help="Playwright PDF page format."),
    ) -> None:
        typer.echo(generate_pdf_file(input_path, output_path, page_format).as_posix())

    @app.command("apply-resume-tailoring")
    def apply_resume_tailoring(
        tailoring_path: Path = typer.Argument(..., exists=True, readable=True, help="Resume-tailoring JSON packet path."),
        base_context_path: Path = typer.Argument(..., exists=True, readable=True, help="Base resume context JSON path."),
        out: Path | None = typer.Option(None, "--out", help="Optional tailored resume context JSON output path."),
        overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing tailored context file."),
    ) -> None:
        try:
            artifacts = apply_resume_tailoring_packet(
                tailoring_path,
                base_context_path,
                out=out,
                overwrite=overwrite,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(artifacts.output_path.as_posix())
