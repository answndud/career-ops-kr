from __future__ import annotations

import json
from pathlib import Path

import typer

from career_ops_kr.commands.ops import run_ops_check
from career_ops_kr.commands.resume import DEFAULT_LIVE_SMOKE_TARGETS_PATH


def _print_verify_summary(result: object) -> None:
    verify = result.verify
    typer.echo(
        "Verify: "
        + ("OK" if verify.ok else "FAIL")
        + f" | missing={len(verify.missing)} | duplicates={len(verify.duplicates)} | missing_reports={len(verify.missing_reports)}"
    )
    for path in verify.missing:
        typer.echo(f"- missing required file: {path}")
    for duplicate in verify.duplicates:
        typer.echo(f"- duplicate tracker row: {duplicate}")
    for report_path in verify.missing_reports:
        typer.echo(f"- missing report file: {report_path}")


def _print_audit_summary(result: object, *, limit: int) -> None:
    audit = result.audit
    typer.echo(
        "Audit: "
        + ("OK" if audit.ok else "FAIL")
        + f" | tracker_rows={audit.tracker_row_count} | findings={len(audit.findings)}"
    )
    if audit.findings:
        for category, count in audit.counts.items():
            typer.echo(f"- audit {category}: {count}")
        for finding in audit.findings[:limit]:
            subject = ""
            if finding.tracker_id:
                subject = f"[{finding.tracker_id}] {finding.company} / {finding.role}: "
            path_suffix = f" ({finding.path})" if finding.path else ""
            typer.echo(f"- {finding.category}: {subject}{finding.message}{path_suffix}")
        remaining = len(audit.findings) - limit
        if remaining > 0:
            typer.echo(f"... {remaining} more audit finding(s)")


def _print_live_smoke_summary(result: object) -> None:
    live_smoke_status = str(result.live_smoke_status).upper()
    scan_summary = result.live_smoke_scan_summary or {"recognized_count": 0, "ignored": []}
    typer.echo(
        f"Live smoke: {live_smoke_status}"
        + f" | recognized_reports={scan_summary.get('recognized_count', 0)}"
    )
    if result.live_smoke_message:
        typer.echo(f"- {result.live_smoke_message}")
    for entry in result.live_smoke_entries:
        age_text = f"{entry.age_hours:.1f}h" if entry.age_hours is not None else "-"
        report_kind = entry.report_type or "-"
        report_path_text = entry.report_path.as_posix() if entry.report_path else "-"
        if entry.status == "ok":
            selection = "fallback" if entry.used_fallback else "primary"
            typer.echo(
                f"- OK {entry.target} | age={age_text} | {report_kind} | {selection} | url={entry.selected_url or '-'} | report={report_path_text}"
            )
            continue
        typer.echo(
            f"- {entry.status.upper()} {entry.target} | age={age_text} | {report_kind} | {entry.message or '-'} | report={report_path_text}"
        )


def register_ops_commands(app: typer.Typer) -> None:
    @app.command("ops-check")
    def ops_check(
        tracker_path: Path = typer.Option(Path("data/applications.md"), "--tracker-path", help="Applications tracker markdown path for audit."),
        repo_root: Path = typer.Option(Path("."), "--repo-root", help="Repository root used to resolve relative tracker artifact paths."),
        output_dir: Path = typer.Option(
            Path("output"),
            "--output-dir",
            help="Output root used by tracker/output audit checks.",
        ),
        audit_limit: int = typer.Option(20, "--audit-limit", min=1, help="Maximum number of audit findings to print in text mode."),
        include_live_smoke: bool = typer.Option(
            True,
            "--live-smoke/--no-live-smoke",
            help="Also evaluate saved live smoke report health.",
        ),
        require_live_smoke: bool = typer.Option(
            False,
            "--require-live-smoke",
            help="Fail when no recognized live smoke reports are available.",
        ),
        live_smoke_dir: Path = typer.Option(
            Path("output"),
            "--live-smoke-dir",
            help="Directory to scan for saved live smoke JSON reports.",
        ),
        live_smoke_targets_path: Path = typer.Option(
            DEFAULT_LIVE_SMOKE_TARGETS_PATH,
            "--live-smoke-targets-path",
            exists=True,
            readable=True,
            help="Live smoke target registry YAML path.",
        ),
        live_smoke_recursive: bool = typer.Option(
            True,
            "--live-smoke-recursive/--no-live-smoke-recursive",
            help="Recursively scan subdirectories for saved live smoke reports.",
        ),
        live_smoke_max_age_hours: float = typer.Option(
            24.0,
            "--live-smoke-max-age-hours",
            min=0.0,
            help="Maximum allowed age for the latest saved live smoke report entry per target.",
        ),
        live_smoke_report_type: str | None = typer.Option(
            None,
            "--live-smoke-type",
            help="Optional live smoke report type filter: single or batch.",
        ),
        live_smoke_target: str | None = typer.Option(
            None,
            "--live-smoke-target",
            help="Only validate a specific live smoke target key.",
        ),
        as_json: bool = typer.Option(False, "--json", help="Print the ops check result as JSON."),
    ) -> None:
        try:
            result = run_ops_check(
                tracker_path=tracker_path,
                repo_root=repo_root,
                output_dir=output_dir,
                include_live_smoke=include_live_smoke,
                require_live_smoke=require_live_smoke,
                live_smoke_dir=live_smoke_dir,
                live_smoke_targets_path=live_smoke_targets_path,
                live_smoke_recursive=live_smoke_recursive,
                live_smoke_max_age_hours=live_smoke_max_age_hours,
                live_smoke_report_type=live_smoke_report_type,
                live_smoke_target=live_smoke_target,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

        if as_json:
            typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            typer.echo("Ops check summary")
            _print_verify_summary(result)
            _print_audit_summary(result, limit=audit_limit)
            _print_live_smoke_summary(result)
            typer.echo("Overall: " + ("OK" if result.ok else "FAIL"))

        if not result.ok:
            raise typer.Exit(code=1)
