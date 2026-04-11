from __future__ import annotations

from pathlib import Path
from typing import Callable

import typer

from career_ops_kr.commands.intake import DEFAULT_SCORECARD_PATH
from career_ops_kr.commands.resume import (
    DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    compare_live_smoke_reports,
    describe_live_smoke_report_filters,
    evaluate_live_smoke_report_health,
    get_live_smoke_report_scan_summary,
    list_latest_live_smoke_entries_by_target,
    list_live_smoke_reports,
    list_live_smoke_targets,
    load_live_smoke_target,
    resolve_latest_live_smoke_report,
    resolve_latest_live_smoke_report_pair,
    summarize_ignored_live_smoke_reports,
    summarize_live_smoke_report,
    write_live_smoke_batch_report,
    write_live_smoke_report,
)


def register_resume_smoke_commands(
    app: typer.Typer,
    *,
    run_live_resume_smoke_func: Callable[..., object],
    run_batch_live_resume_smoke_func: Callable[..., object],
) -> None:
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
            artifacts = run_live_resume_smoke_func(
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
            result = run_batch_live_resume_smoke_func(
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
