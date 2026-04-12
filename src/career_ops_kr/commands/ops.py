from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from career_ops_kr.commands.resume import (
    DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    evaluate_live_smoke_report_health,
    get_live_smoke_report_scan_summary,
)
from career_ops_kr.commands.tracker import VerifyResult, run_audit_jobs, run_verify
from career_ops_kr.resume_pipeline.models import LiveSmokeReportHealthEntry
from career_ops_kr.tracker import TrackerAuditResult


def _live_smoke_entry_to_dict(entry: LiveSmokeReportHealthEntry) -> dict[str, Any]:
    return {
        "target": entry.target,
        "status": entry.status,
        "generated_at": entry.generated_at,
        "age_hours": entry.age_hours,
        "report_path": entry.report_path.as_posix() if entry.report_path else None,
        "report_type": entry.report_type,
        "selected_url": entry.selected_url,
        "used_fallback": entry.used_fallback,
        "message": entry.message,
    }


@dataclass(slots=True)
class OpsCheckResult:
    verify: VerifyResult
    audit: TrackerAuditResult
    live_smoke_status: str
    live_smoke_entries: list[LiveSmokeReportHealthEntry]
    live_smoke_scan_summary: dict[str, Any] | None
    live_smoke_message: str | None = None

    @property
    def live_smoke_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.live_smoke_entries:
            counts[entry.status] = counts.get(entry.status, 0) + 1
        return counts

    @property
    def live_smoke_ok(self) -> bool:
        return self.live_smoke_status in {"ok", "skipped", "disabled"}

    @property
    def ok(self) -> bool:
        return self.verify.ok and self.audit.ok and self.live_smoke_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verify": {
                "ok": self.verify.ok,
                "missing": self.verify.missing,
                "duplicates": self.verify.duplicates,
                "missing_reports": self.verify.missing_reports,
            },
            "audit": {
                "ok": self.audit.ok,
                **self.audit.to_dict(),
            },
            "live_smoke": {
                "status": self.live_smoke_status,
                "ok": self.live_smoke_ok,
                "message": self.live_smoke_message,
                "counts": self.live_smoke_counts,
                "scan_summary": self.live_smoke_scan_summary,
                "entries": [_live_smoke_entry_to_dict(entry) for entry in self.live_smoke_entries],
            },
        }


def run_ops_check(
    *,
    tracker_path: Path,
    repo_root: Path,
    output_dir: Path,
    include_live_smoke: bool = True,
    require_live_smoke: bool = False,
    live_smoke_dir: Path = Path("output"),
    live_smoke_targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    live_smoke_recursive: bool = True,
    live_smoke_max_age_hours: float = 24.0,
    live_smoke_report_type: str | None = None,
    live_smoke_target: str | None = None,
) -> OpsCheckResult:
    verify_result = run_verify()
    audit_result = run_audit_jobs(
        tracker_path,
        repo_root=repo_root,
        output_dir=output_dir,
    )

    if not include_live_smoke:
        return OpsCheckResult(
            verify=verify_result,
            audit=audit_result,
            live_smoke_status="disabled",
            live_smoke_entries=[],
            live_smoke_scan_summary=None,
            live_smoke_message="Live smoke report health check disabled.",
        )

    scan_summary = get_live_smoke_report_scan_summary(
        live_smoke_dir,
        recursive=live_smoke_recursive,
    )
    recognized_count = int(scan_summary.get("recognized_count", 0))
    if recognized_count == 0:
        return OpsCheckResult(
            verify=verify_result,
            audit=audit_result,
            live_smoke_status="failing" if require_live_smoke else "skipped",
            live_smoke_entries=[],
            live_smoke_scan_summary=scan_summary,
            live_smoke_message=(
                f"No recognized live smoke reports found in {live_smoke_dir.as_posix()}."
            ),
        )

    health_entries, health_scan_summary = evaluate_live_smoke_report_health(
        live_smoke_dir,
        targets_path=live_smoke_targets_path,
        recursive=live_smoke_recursive,
        max_age_hours=live_smoke_max_age_hours,
        report_type=live_smoke_report_type,
        target=live_smoke_target,
    )
    if not health_entries:
        return OpsCheckResult(
            verify=verify_result,
            audit=audit_result,
            live_smoke_status="failing",
            live_smoke_entries=[],
            live_smoke_scan_summary=health_scan_summary,
            live_smoke_message=(
                f"No matching live smoke targets found in {live_smoke_targets_path.as_posix()}."
            ),
        )

    failing_entries = [entry for entry in health_entries if entry.status != "ok"]
    return OpsCheckResult(
        verify=verify_result,
        audit=audit_result,
        live_smoke_status="ok" if not failing_entries else "failing",
        live_smoke_entries=health_entries,
        live_smoke_scan_summary=health_scan_summary,
        live_smoke_message=(
            f"Validated latest live smoke report status for {len(health_entries)} target(s)."
        ),
    )
