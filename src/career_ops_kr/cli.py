from __future__ import annotations

from pathlib import Path

import httpx
import typer

from career_ops_kr.commands.intake import (
    DEFAULT_PROFILE_PATH,
    DEFAULT_SCORECARD_PATH,
    run_discover_jobs,
    run_process_pipeline,
    run_score_job,
)
from career_ops_kr.commands.research import (
    COMPANY_RESEARCH_PROMPT_PATH,
    run_prepare_company_followup,
    run_prepare_company_research,
)
from career_ops_kr.commands.resume import (
    compare_live_smoke_reports,
    DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    build_tailored_resume,
    build_tailored_resume_from_url,
    apply_resume_tailoring_packet,
    describe_live_smoke_report_filters,
    evaluate_live_smoke_report_health,
    get_live_smoke_report_scan_summary,
    run_batch_live_resume_smoke,
    create_resume_tailoring_packet,
    generate_pdf_file,
    list_live_smoke_reports,
    list_latest_live_smoke_entries_by_target,
    list_live_smoke_targets,
    load_live_smoke_target,
    render_resume_html,
    resolve_latest_live_smoke_report,
    resolve_latest_live_smoke_report_pair,
    run_live_resume_smoke,
    summarize_ignored_live_smoke_reports,
    summarize_live_smoke_report,
    write_live_smoke_report,
    write_live_smoke_batch_report,
)
from career_ops_kr.commands.tracker import run_merge_tracker, run_normalize_statuses, run_verify
from career_ops_kr.jobs import fetch_job_to_markdown
from career_ops_kr.pipeline import PipelineLockError
from career_ops_kr.scoring import ScoreJobError


app = typer.Typer(help="Codex-first job search operations toolkit for Korean developers.")


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


@app.command("smoke-live-resume")
def smoke_live_resume(
    target: str = typer.Option(
        "remember_platform_ko",
        "--target",
        help="Named live smoke target from config/live-smoke-targets.yml.",
    ),
    targets_path: Path = typer.Option(
        DEFAULT_LIVE_SMOKE_TARGETS_PATH,
        "--targets-path",
        exists=True,
        readable=True,
        help="Live smoke target registry YAML path.",
    ),
    url: str = typer.Option(
        "",
        "--url",
        help="Public job posting URL override for the live smoke run.",
    ),
    base_context_path: Path = typer.Option(
        None,
        "--base-context-path",
        help="Base resume context JSON override for the live smoke run.",
    ),
    template_path: Path = typer.Option(
        None,
        "--template-path",
        help="Resume template HTML override for the live smoke run.",
    ),
    profile_path: Path = typer.Option(
        None,
        "--profile-path",
        help="Candidate profile YAML override for the live smoke run.",
    ),
    scorecard_path: Path = typer.Option(
        DEFAULT_SCORECARD_PATH,
        "--scorecard-path",
        exists=True,
        readable=True,
        help="Scorecard YAML used for scoring and resume keyword hints.",
    ),
    source: str | None = typer.Option(None, "--source", help="Optional source override."),
    out_dir: Path | None = typer.Option(None, "--out-dir", help="Optional output directory for smoke artifacts."),
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Disable TLS certificate verification when local Python CA setup is broken.",
    ),
    keep_artifacts: bool = typer.Option(
        False,
        "--keep-artifacts",
        help="Keep smoke artifacts on disk instead of cleaning them after success.",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing --out-dir."),
    pdf: bool = typer.Option(False, "--pdf", help="Also render PDF during the live smoke run."),
    pdf_format: str = typer.Option("A4", "--pdf-format", help="Playwright PDF page format when --pdf is set."),
    report_out: Path | None = typer.Option(
        None,
        "--report-out",
        help="Optional JSON report path for single-target live smoke results.",
    ),
) -> None:
    resolved_display_url = url
    if not resolved_display_url:
        try:
            resolved_display_url = load_live_smoke_target(target, targets_path).candidates[0].url
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    try:
        artifacts = run_live_resume_smoke(
            target_key=target,
            targets_path=targets_path,
            url=url or None,
            base_context_path=base_context_path,
            template_path=template_path,
            profile_path=profile_path,
            scorecard_path=scorecard_path,
            source=source,
            out_dir=out_dir,
            insecure=insecure,
            keep_artifacts=keep_artifacts,
            overwrite=overwrite,
            pdf=pdf,
            pdf_format=pdf_format,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Live smoke OK for {resolved_display_url}")
    typer.echo(f"Run dir: {artifacts.run_dir.as_posix()}")
    typer.echo(f"Selected URL: {artifacts.selected_url}")
    if artifacts.used_fallback:
        typer.echo(f"Selected candidate: {artifacts.candidate_label or 'fallback'}")
    if report_out:
        try:
            written_report = write_live_smoke_report(
                artifacts,
                targets_path=targets_path,
                target_key=None if url else (target or None),
                output_path=report_out,
                overwrite=overwrite,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Smoke report: {written_report.as_posix()}")
    typer.echo(f"Job: {artifacts.job_path.as_posix()}")
    typer.echo(f"Report: {artifacts.report_path.as_posix()}")
    typer.echo(f"Tailoring: {artifacts.tailoring_path.as_posix()}")
    typer.echo(f"Tailored context: {artifacts.tailored_context_path.as_posix()}")
    typer.echo(f"HTML: {artifacts.html_path.as_posix()}")
    if artifacts.pdf_path:
        typer.echo(f"PDF: {artifacts.pdf_path.as_posix()}")
    if artifacts.cleaned:
        typer.echo("Artifacts cleaned after successful smoke run.")


@app.command("list-live-smoke-targets")
def list_live_smoke_targets_command(
    targets_path: Path = typer.Option(
        DEFAULT_LIVE_SMOKE_TARGETS_PATH,
        "--targets-path",
        exists=True,
        readable=True,
        help="Live smoke target registry YAML path.",
    ),
) -> None:
    try:
        targets = list_live_smoke_targets(targets_path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for target in targets:
        description_suffix = f" | {target.description}" if target.description else ""
        primary = target.candidates[0]
        typer.echo(
            f"{target.key}: {primary.url} | source={primary.source or 'auto'}"
            f" | candidates={len(target.candidates)}"
            f" | context={target.base_context_path.as_posix()}"
            f" | template={target.template_path.as_posix()}"
            f" | profile={target.profile_path.as_posix()}"
            f"{description_suffix}"
        )


@app.command("show-live-smoke-report")
def show_live_smoke_report_command(
    report_path: Path | None = typer.Argument(None, exists=True, readable=True, help="Single or batch live smoke JSON report."),
    latest_from: Path | None = typer.Option(
        None,
        "--latest-from",
        exists=True,
        readable=True,
        help="Resolve and show the latest matching report from a directory instead of passing a report path directly.",
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Recursively scan subdirectories when using --latest-from.",
    ),
    report_type: str | None = typer.Option(
        None,
        "--type",
        help="Optional report type filter for --latest-from: single or batch.",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Only consider reports related to a specific live smoke target when using --latest-from.",
    ),
    used_fallback_only: bool = typer.Option(
        False,
        "--used-fallback-only",
        help="Only consider reports where a fallback candidate was used at least once when using --latest-from.",
    ),
    failed_only: bool = typer.Option(
        False,
        "--failed-only",
        help="Only consider reports with one or more failures when using --latest-from.",
    ),
) -> None:
    try:
        if report_path and latest_from:
            raise typer.BadParameter("Pass a report path or use --latest-from, not both.")
        if not report_path and not latest_from:
            raise typer.BadParameter("Pass a report path or use --latest-from.")
        resolved_report_path = report_path
        if latest_from:
            resolved_report_path = resolve_latest_live_smoke_report(
                latest_from,
                recursive=recursive,
                report_type=report_type,
                target=target,
                used_fallback_only=used_fallback_only,
                failed_only=failed_only,
            )
        if resolved_report_path is None:
            raise typer.BadParameter("Pass a report path or use --latest-from.")
        lines = summarize_live_smoke_report(resolved_report_path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for line in lines:
        typer.echo(line)


@app.command("list-live-smoke-reports")
def list_live_smoke_reports_command(
    directory: Path = typer.Argument(Path("output"), exists=True, readable=True, help="Directory to scan for saved live smoke JSON reports."),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Recursively scan subdirectories for report JSON files.",
    ),
    report_type: str | None = typer.Option(
        None,
        "--type",
        help="Optional report type filter: single or batch.",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Only show reports related to a specific live smoke target key.",
    ),
    latest: int | None = typer.Option(
        None,
        "--latest",
        min=1,
        help="Only show the latest N matching reports.",
    ),
    latest_per_target: bool = typer.Option(
        False,
        "--latest-per-target",
        help="Show only the latest matching entry for each target instead of report-level inventory.",
    ),
    used_fallback_only: bool = typer.Option(
        False,
        "--used-fallback-only",
        help="Only show reports where a fallback candidate was used at least once.",
    ),
    failed_only: bool = typer.Option(
        False,
        "--failed-only",
        help="Only show reports with one or more failures.",
    ),
) -> None:
    if latest is not None and latest_per_target:
        raise typer.BadParameter("Use --latest or --latest-per-target, not both.")
    try:
        if latest_per_target:
            entries = list_latest_live_smoke_entries_by_target(
                directory,
                recursive=recursive,
                report_type=report_type,
                target=target,
                used_fallback_only=used_fallback_only,
                failed_only=failed_only,
            )
            reports: list[dict[str, object]] = []
        else:
            reports = list_live_smoke_reports(
                directory,
                recursive=recursive,
                report_type=report_type,
                target=target,
                latest=latest,
                used_fallback_only=used_fallback_only,
                failed_only=failed_only,
            )
            entries = []
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not reports and not entries:
        filter_summary = describe_live_smoke_report_filters(
            report_type=report_type,
            target=target,
            used_fallback_only=used_fallback_only,
            failed_only=failed_only,
        )
        scan_summary = get_live_smoke_report_scan_summary(directory, recursive=recursive)
        ignored_summary = summarize_ignored_live_smoke_reports(scan_summary["ignored"])
        typer.echo(
            f"No matching live smoke reports found in {directory.as_posix()} | "
            f"filters: {filter_summary} | recognized reports: {scan_summary['recognized_count']} | {ignored_summary}"
        )
        return

    if entries:
        for entry in entries:
            generated_at = entry.get("generated_at") or "unknown"
            path = entry["path"].as_posix()
            report_kind = entry.get("report_type") or "unknown"
            if entry.get("status") == "failure":
                typer.echo(
                    f"{entry['target']} | {generated_at} | failure | {report_kind} "
                    f"| message={entry.get('message', '-')} | report={path}"
                )
                continue
            mode = "fallback" if entry.get("used_fallback") else "primary"
            typer.echo(
                f"{entry['target']} | {generated_at} | success | {report_kind} "
                f"| url={entry.get('selected_url')} | {mode} | report={path}"
            )
        return

    for report in reports:
        path = report["path"].as_posix()
        generated_at = report.get("generated_at") or "unknown"
        if report["type"] == "single":
            mode = "fallback" if report.get("used_fallback") else "primary"
            typer.echo(
                f"{path} | single | {generated_at} | target={report.get('target')} "
                f"| url={report.get('selected_url')} | {mode}"
            )
            continue

        selected_targets = report.get("selected_targets") or []
        target_summary = ",".join(selected_targets) if selected_targets else "all"
        typer.echo(
            f"{path} | batch | {generated_at} | targets={target_summary} "
            f"| success={report.get('success_count', 0)} | failure={report.get('failure_count', 0)} "
            f"| fallback-hits={report.get('fallback_success_count', 0)}"
        )


@app.command("compare-live-smoke-reports")
def compare_live_smoke_reports_command(
    base_report_path: Path | None = typer.Argument(None, exists=True, readable=True, help="Earlier single or batch live smoke JSON report."),
    current_report_path: Path | None = typer.Argument(None, exists=True, readable=True, help="Later single or batch live smoke JSON report."),
    latest_from: Path | None = typer.Option(
        None,
        "--latest-from",
        exists=True,
        readable=True,
        help="Resolve the latest two matching reports from a directory instead of passing both report paths directly.",
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Recursively scan subdirectories when using --latest-from.",
    ),
    report_type: str | None = typer.Option(
        None,
        "--type",
        help="Optional report type filter for --latest-from: single or batch.",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Only consider reports related to a specific live smoke target when using --latest-from.",
    ),
    used_fallback_only: bool = typer.Option(
        False,
        "--used-fallback-only",
        help="Only consider reports where a fallback candidate was used at least once when using --latest-from.",
    ),
    failed_only: bool = typer.Option(
        False,
        "--failed-only",
        help="Only consider reports with one or more failures when using --latest-from.",
    ),
) -> None:
    try:
        if latest_from and (base_report_path or current_report_path):
            raise typer.BadParameter("Pass two report paths or use --latest-from, not both.")
        if latest_from:
            resolved_base_report_path, resolved_current_report_path = resolve_latest_live_smoke_report_pair(
                latest_from,
                recursive=recursive,
                report_type=report_type,
                target=target,
                used_fallback_only=used_fallback_only,
                failed_only=failed_only,
            )
        else:
            if not base_report_path or not current_report_path:
                raise typer.BadParameter("Pass both report paths or use --latest-from.")
            resolved_base_report_path = base_report_path
            resolved_current_report_path = current_report_path
        lines = compare_live_smoke_reports(resolved_base_report_path, resolved_current_report_path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for line in lines:
        typer.echo(line)


@app.command("validate-live-smoke-targets")
def validate_live_smoke_targets_command(
    targets_path: Path = typer.Option(
        DEFAULT_LIVE_SMOKE_TARGETS_PATH,
        "--targets-path",
        exists=True,
        readable=True,
        help="Live smoke target registry YAML path.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit nonzero when any live smoke target still has only one candidate URL.",
    ),
    max_candidates: int | None = typer.Option(
        None,
        "--max-candidates",
        min=1,
        help="Optional maximum allowed candidate count per target. Exit nonzero when exceeded.",
    ),
) -> None:
    try:
        targets = list_live_smoke_targets(targets_path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    targets_with_fallbacks = sum(1 for target in targets if len(target.candidates) > 1)
    single_candidate_targets = [target.key for target in targets if len(target.candidates) == 1]
    crowded_targets = [target.key for target in targets if len(target.candidates) > 2]
    too_many_targets = (
        [target.key for target in targets if len(target.candidates) > max_candidates]
        if max_candidates is not None
        else []
    )
    coverage_ratio = f"{targets_with_fallbacks}/{len(targets)}"
    typer.echo(
        f"Validated {len(targets)} live smoke target(s) from {targets_path.as_posix()}."
    )
    typer.echo(f"Targets with fallback candidates: {targets_with_fallbacks}")
    typer.echo(f"Fallback coverage: {coverage_ratio}")
    typer.echo(f"Targets with more than 2 candidates: {len(crowded_targets)}")
    if crowded_targets:
        typer.echo("Crowded targets: " + ", ".join(crowded_targets))
        typer.echo(
            "Warning: some live smoke targets have more than 2 candidates. Consider pruning or splitting them.",
            err=True,
        )
    if too_many_targets:
        typer.echo(
            f"Targets exceeding max candidates ({max_candidates}): " + ", ".join(too_many_targets),
            err=True,
        )
        raise typer.Exit(code=1)
    if single_candidate_targets:
        typer.echo(
            "Single-candidate targets: " + ", ".join(single_candidate_targets)
        )
        typer.echo("Warning: some live smoke targets still depend on a single public URL.", err=True)
        if strict:
            raise typer.Exit(code=1)
        return

    typer.echo("Single-candidate targets: none")


@app.command("validate-live-smoke-reports")
def validate_live_smoke_reports_command(
    directory: Path = typer.Argument(Path("output"), exists=True, readable=True, help="Directory to scan for saved live smoke JSON reports."),
    targets_path: Path = typer.Option(
        DEFAULT_LIVE_SMOKE_TARGETS_PATH,
        "--targets-path",
        exists=True,
        readable=True,
        help="Live smoke target registry YAML path.",
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Recursively scan subdirectories for report JSON files.",
    ),
    max_age_hours: float = typer.Option(
        24.0,
        "--max-age-hours",
        min=0.0,
        help="Maximum allowed age for the latest saved report entry per target.",
    ),
    report_type: str | None = typer.Option(
        None,
        "--type",
        help="Optional report type filter: single or batch.",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Only validate a specific live smoke target key.",
    ),
) -> None:
    try:
        health_entries, scan_summary = evaluate_live_smoke_report_health(
            directory,
            targets_path=targets_path,
            recursive=recursive,
            max_age_hours=max_age_hours,
            report_type=report_type,
            target=target,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if not health_entries:
        typer.echo(
            f"No matching live smoke targets found in {targets_path.as_posix()}."
        )
        raise typer.Exit(code=1)

    typer.echo(
        f"Validated latest live smoke report status for {len(health_entries)} target(s) from {directory.as_posix()}."
    )
    typer.echo(
        f"Recognized reports: {scan_summary['recognized_count']} | {summarize_ignored_live_smoke_reports(scan_summary['ignored'])}"
    )

    failing_entries = 0
    for entry in health_entries:
        age_text = f"{entry.age_hours:.1f}h" if entry.age_hours is not None else "-"
        report_kind = entry.report_type or "-"
        report_path_text = entry.report_path.as_posix() if entry.report_path else "-"
        if entry.status == "ok":
            selection = "fallback" if entry.used_fallback else "primary"
            typer.echo(
                f"OK {entry.target} | age={age_text} | {report_kind} | {selection} | url={entry.selected_url or '-'} | report={report_path_text}"
            )
            continue

        failing_entries += 1
        typer.echo(
            f"{entry.status.upper()} {entry.target} | age={age_text} | {report_kind} | {entry.message or '-'} | report={report_path_text}",
            err=True,
        )

    ok_count = len(health_entries) - failing_entries
    typer.echo(
        f"Live smoke report health summary: {ok_count} ok, {failing_entries} failing."
    )
    if failing_entries:
        raise typer.Exit(code=1)


@app.command("smoke-live-resume-batch")
def smoke_live_resume_batch(
    target: list[str] = typer.Option(
        None,
        "--target",
        help="Repeatable live smoke target key. Omit to run every registered target.",
    ),
    targets_path: Path = typer.Option(
        DEFAULT_LIVE_SMOKE_TARGETS_PATH,
        "--targets-path",
        exists=True,
        readable=True,
        help="Live smoke target registry YAML path.",
    ),
    scorecard_path: Path = typer.Option(
        DEFAULT_SCORECARD_PATH,
        "--scorecard-path",
        exists=True,
        readable=True,
        help="Scorecard YAML used for scoring and resume keyword hints.",
    ),
    out_root: Path | None = typer.Option(
        None,
        "--out-root",
        help="Optional root directory for per-target smoke artifacts.",
    ),
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Disable TLS certificate verification when local Python CA setup is broken.",
    ),
    keep_artifacts: bool = typer.Option(
        False,
        "--keep-artifacts",
        help="Keep smoke artifacts on disk instead of cleaning them after success.",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing --out-root/<target> directory."),
    pdf: bool = typer.Option(False, "--pdf", help="Also render PDF during the live smoke run."),
    pdf_format: str = typer.Option("A4", "--pdf-format", help="Playwright PDF page format when --pdf is set."),
    report_out: Path | None = typer.Option(
        None,
        "--report-out",
        help="Optional JSON report path for batch smoke results.",
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--fail-fast",
        help="Continue running later targets after a failure.",
    ),
) -> None:
    try:
        result = run_batch_live_resume_smoke(
            target_keys=target or None,
            targets_path=targets_path,
            scorecard_path=scorecard_path,
            out_root=out_root,
            insecure=insecure,
            keep_artifacts=keep_artifacts,
            overwrite=overwrite,
            pdf=pdf,
            pdf_format=pdf_format,
            continue_on_error=continue_on_error,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for target_key, artifacts in result.successes:
        cleaned = "cleaned" if artifacts.cleaned else "kept"
        fallback = "fallback" if artifacts.used_fallback else "primary"
        label = getattr(artifacts, "candidate_label", None)
        label_suffix = f" | label={label}" if label else ""
        typer.echo(
            f"OK {target_key} | {artifacts.selected_url} | {fallback}{label_suffix} | {artifacts.run_dir.as_posix()} | {cleaned}"
        )
    for target_key, message in result.failures:
        typer.echo(f"FAILED {target_key} | {message}", err=True)

    if report_out:
        try:
            written_report = write_live_smoke_batch_report(
                result,
                targets_path=targets_path,
                selected_targets=target or None,
                output_path=report_out,
                overwrite=overwrite,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Batch report: {written_report.as_posix()}")

    typer.echo(
        f"Batch live smoke summary: {len(result.successes)} passed, {len(result.failures)} failed."
    )
    if result.failures:
        raise typer.Exit(code=1)


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
        verify()
    typer.echo("Tracker finalize complete.")


@app.command("verify")
def verify() -> None:
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


def main() -> None:
    app()
