from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_ops_kr.resume_pipeline.models import (
    BatchLiveResumeSmokeResult,
    LiveResumeSmokeArtifacts,
    LiveResumeSmokeCandidate,
    LiveResumeSmokeTarget,
    LiveSmokeReportHealthEntry,
)
from career_ops_kr.utils import ensure_dir, load_yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIVE_SMOKE_TARGETS_PATH = REPO_ROOT / "config" / "live-smoke-targets.yml"


def live_smoke_report_metadata(report_path: Path) -> dict[str, Any]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    if "successes" in payload and "failures" in payload:
        selected_targets = [str(item) for item in (payload.get("selected_targets") or [])]
        if not selected_targets:
            selected_targets = sorted(
                {
                    str(item.get("target"))
                    for item in [*(payload.get("successes") or []), *(payload.get("failures") or [])]
                    if item.get("target")
                }
            )
        fallback_success_count = sum(
            1 for success in (payload.get("successes") or []) if success.get("used_fallback")
        )
        success_count = int(payload.get("success_count", 0))
        failure_count = int(payload.get("failure_count", 0))
        return {
            "path": report_path,
            "type": "batch",
            "generated_at": payload.get("generated_at"),
            "selected_targets": selected_targets,
            "targets": selected_targets,
            "success_count": success_count,
            "failure_count": failure_count,
            "fallback_success_count": fallback_success_count,
            "has_fallback": fallback_success_count > 0,
            "has_failures": failure_count > 0,
        }

    if "selected_url" in payload:
        target = str(payload.get("target") or "manual override")
        used_fallback = bool(payload.get("used_fallback"))
        return {
            "path": report_path,
            "type": "single",
            "generated_at": payload.get("generated_at"),
            "target": target,
            "targets": [target],
            "selected_url": payload.get("selected_url"),
            "used_fallback": used_fallback,
            "candidate_label": payload.get("candidate_label"),
            "has_fallback": used_fallback,
            "has_failures": False,
        }

    raise ValueError(f"Unrecognized live smoke report schema: {report_path.as_posix()}")


def _normalize_live_smoke_report_type(report_type: str | None) -> str | None:
    if report_type is None:
        return None
    normalized_type = report_type.strip().lower()
    if normalized_type not in {"single", "batch"}:
        raise ValueError(f"Unsupported live smoke report type filter: {report_type}")
    return normalized_type


def _parse_live_smoke_generated_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _scan_live_smoke_reports(
    directory: Path,
    *,
    recursive: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    globber = directory.rglob if recursive else directory.glob
    reports: list[dict[str, Any]] = []
    ignored: list[str] = []
    for path in globber("*.json"):
        if not path.is_file():
            continue
        try:
            metadata = live_smoke_report_metadata(path)
        except json.JSONDecodeError:
            ignored.append(f"invalid JSON: {path.as_posix()}")
            continue
        except ValueError:
            ignored.append(f"unrecognized schema: {path.as_posix()}")
            continue
        reports.append(metadata)
    return reports, ignored


def describe_live_smoke_report_filters(
    *,
    report_type: str | None = None,
    target: str | None = None,
    used_fallback_only: bool = False,
    failed_only: bool = False,
) -> str:
    parts: list[str] = []
    normalized_type = (
        _normalize_live_smoke_report_type(report_type) if report_type is not None else None
    )
    if normalized_type:
        parts.append(f"type={normalized_type}")
    if target:
        parts.append(f"target={target.strip()}")
    if used_fallback_only:
        parts.append("used_fallback_only=true")
    if failed_only:
        parts.append("failed_only=true")
    return ", ".join(parts) if parts else "none"


def summarize_ignored_live_smoke_reports(ignored: list[str], *, limit: int = 3) -> str:
    if not ignored:
        return "Ignored invalid/unrecognized JSON files: 0."
    shown = ignored[:limit]
    suffix = "" if len(ignored) <= limit else f" (+{len(ignored) - limit} more)"
    return (
        f"Ignored invalid/unrecognized JSON files: {len(ignored)} | "
        + "; ".join(shown)
        + suffix
    )


def get_live_smoke_report_scan_summary(directory: Path, *, recursive: bool = True) -> dict[str, Any]:
    reports, ignored = _scan_live_smoke_reports(directory, recursive=recursive)
    return {
        "recognized_count": len(reports),
        "ignored": ignored,
    }


def list_live_smoke_reports(
    directory: Path,
    *,
    recursive: bool = True,
    report_type: str | None = None,
    target: str | None = None,
    latest: int | None = None,
    used_fallback_only: bool = False,
    failed_only: bool = False,
) -> list[dict[str, Any]]:
    normalized_type = _normalize_live_smoke_report_type(report_type)
    normalized_target = target.strip() if target else None

    reports, _ignored = _scan_live_smoke_reports(directory, recursive=recursive)
    filtered_reports: list[dict[str, Any]] = []
    for metadata in reports:
        if normalized_type and metadata["type"] != normalized_type:
            continue
        if normalized_target and normalized_target not in metadata.get("targets", []):
            continue
        if used_fallback_only and not metadata.get("has_fallback"):
            continue
        if failed_only and not metadata.get("has_failures"):
            continue
        filtered_reports.append(metadata)

    filtered_reports.sort(
        key=lambda item: (
            str(item.get("generated_at") or ""),
            item["path"].as_posix(),
        ),
        reverse=True,
    )
    if latest is not None:
        return filtered_reports[:latest]
    return filtered_reports


def _live_smoke_report_entries(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if "successes" in payload and "failures" in payload:
        entries: dict[str, dict[str, Any]] = {}
        for success in payload.get("successes", []):
            target = str(success.get("target", "-"))
            entries[target] = {
                "status": "success",
                "selected_url": success.get("selected_url"),
                "used_fallback": bool(success.get("used_fallback")),
                "candidate_label": success.get("candidate_label"),
                "cleaned": success.get("cleaned"),
            }
        for failure in payload.get("failures", []):
            target = str(failure.get("target", "-"))
            entries[target] = {
                "status": "failure",
                "message": failure.get("message"),
            }
        return entries

    if "selected_url" in payload:
        target = str(payload.get("target") or "manual override")
        return {
            target: {
                "status": "success",
                "selected_url": payload.get("selected_url"),
                "used_fallback": bool(payload.get("used_fallback")),
                "candidate_label": payload.get("candidate_label"),
                "cleaned": payload.get("cleaned"),
            }
        }

    raise ValueError("Unrecognized live smoke report schema.")


def list_latest_live_smoke_entries_by_target(
    directory: Path,
    *,
    recursive: bool = True,
    report_type: str | None = None,
    target: str | None = None,
    used_fallback_only: bool = False,
    failed_only: bool = False,
) -> list[dict[str, Any]]:
    normalized_type = _normalize_live_smoke_report_type(report_type)
    normalized_target = target.strip() if target else None
    reports, _ignored = _scan_live_smoke_reports(directory, recursive=recursive)
    latest_by_target: dict[str, dict[str, Any]] = {}

    for report in reports:
        if normalized_type and report["type"] != normalized_type:
            continue
        payload = json.loads(report["path"].read_text(encoding="utf-8"))
        entries = _live_smoke_report_entries(payload)
        generated_at = report.get("generated_at")
        for target_key, entry in entries.items():
            if normalized_target and target_key != normalized_target:
                continue
            if used_fallback_only and not entry.get("used_fallback"):
                continue
            if failed_only and entry.get("status") != "failure":
                continue
            entry_record = {
                "target": target_key,
                "generated_at": generated_at,
                "path": report["path"],
                "report_type": report["type"],
                **entry,
            }
            previous = latest_by_target.get(target_key)
            if previous is None:
                latest_by_target[target_key] = entry_record
                continue
            previous_key = (
                str(previous.get("generated_at") or ""),
                previous["path"].as_posix(),
            )
            current_key = (
                str(entry_record.get("generated_at") or ""),
                entry_record["path"].as_posix(),
            )
            if current_key > previous_key:
                latest_by_target[target_key] = entry_record

    results = list(latest_by_target.values())
    results.sort(
        key=lambda item: (
            item["target"],
            str(item.get("generated_at") or ""),
            item["path"].as_posix(),
        )
    )
    return results


def list_live_smoke_targets(
    targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
) -> list[LiveResumeSmokeTarget]:
    if not targets_path.exists():
        raise ValueError(f"Live smoke targets config does not exist: {targets_path.as_posix()}")

    payload = load_yaml(targets_path)
    raw_targets = payload.get("targets", {})
    if not isinstance(raw_targets, dict) or not raw_targets:
        raise ValueError(f"Live smoke targets config is missing 'targets': {targets_path.as_posix()}")

    targets: list[LiveResumeSmokeTarget] = []
    for key, raw_target in raw_targets.items():
        if not isinstance(raw_target, dict):
            raise ValueError(f"Live smoke target '{key}' must be a mapping: {targets_path.as_posix()}")
        try:
            raw_url = str(raw_target["url"]).strip() if raw_target.get("url") else ""
            base_context_path = REPO_ROOT / str(raw_target["base_context_path"]).strip()
            template_path = REPO_ROOT / str(raw_target["template_path"]).strip()
            profile_path = REPO_ROOT / str(raw_target["profile_path"]).strip()
        except KeyError as exc:
            raise ValueError(
                f"Live smoke target '{key}' is missing required field '{exc.args[0]}': {targets_path.as_posix()}"
            ) from exc

        for label, path in (
            ("base_context_path", base_context_path),
            ("template_path", template_path),
            ("profile_path", profile_path),
        ):
            if not path.exists():
                raise ValueError(
                    f"Live smoke target '{key}' points to missing {label}: {path.as_posix()}"
                )

        raw_candidates = raw_target.get("candidates", [])
        candidates: list[LiveResumeSmokeCandidate] = []
        if isinstance(raw_candidates, list):
            for index, raw_candidate in enumerate(raw_candidates):
                if not isinstance(raw_candidate, dict) or not raw_candidate.get("url"):
                    raise ValueError(
                        f"Live smoke target '{key}' has invalid candidate at index {index}: {targets_path.as_posix()}"
                    )
                candidates.append(
                    LiveResumeSmokeCandidate(
                        url=str(raw_candidate["url"]).strip(),
                        source=(
                            str(raw_candidate.get("source")).strip().lower()
                            if raw_candidate.get("source")
                            else None
                        ),
                        label=(
                            str(raw_candidate.get("label")).strip()
                            if raw_candidate.get("label")
                            else None
                        ),
                    )
                )
        if raw_url:
            candidates.insert(
                0,
                LiveResumeSmokeCandidate(
                    url=raw_url,
                    source=(
                        str(raw_target.get("source")).strip().lower()
                        if raw_target.get("source")
                        else None
                    ),
                    label="primary",
                ),
            )
        if not candidates:
            raise ValueError(
                f"Live smoke target '{key}' must define url or candidates: {targets_path.as_posix()}"
            )

        targets.append(
            LiveResumeSmokeTarget(
                key=str(key),
                candidates=candidates,
                base_context_path=base_context_path,
                template_path=template_path,
                profile_path=profile_path,
                description=str(raw_target.get("description", "")).strip(),
            )
        )
    return targets


def load_live_smoke_target(
    target_key: str,
    targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
) -> LiveResumeSmokeTarget:
    targets = list_live_smoke_targets(targets_path)
    for target in targets:
        if target.key == target_key:
            return target
    available = ", ".join(target.key for target in targets)
    raise ValueError(f"Unknown live smoke target '{target_key}'. Available targets: {available}")


def evaluate_live_smoke_report_health(
    directory: Path,
    *,
    targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    recursive: bool = True,
    max_age_hours: float = 24.0,
    report_type: str | None = None,
    target: str | None = None,
    now: datetime | None = None,
) -> tuple[list[LiveSmokeReportHealthEntry], dict[str, Any]]:
    normalized_target = target.strip() if target else None
    registry_targets = list_live_smoke_targets(targets_path)
    selected_registry_targets = [
        item for item in registry_targets if not normalized_target or item.key == normalized_target
    ]
    latest_entries = {
        item["target"]: item
        for item in list_latest_live_smoke_entries_by_target(
            directory,
            recursive=recursive,
            report_type=report_type,
            target=normalized_target,
        )
    }
    current_time = now or datetime.now(UTC)
    health_entries: list[LiveSmokeReportHealthEntry] = []
    for registry_target in selected_registry_targets:
        latest_entry = latest_entries.get(registry_target.key)
        if latest_entry is None:
            health_entries.append(
                LiveSmokeReportHealthEntry(
                    target=registry_target.key,
                    status="missing",
                    generated_at=None,
                    age_hours=None,
                    report_path=None,
                    report_type=None,
                    message="No saved report entry for this target.",
                )
            )
            continue

        generated_at = latest_entry.get("generated_at")
        parsed_generated_at = _parse_live_smoke_generated_at(generated_at)
        age_hours = None
        if parsed_generated_at is not None:
            age_hours = max((current_time - parsed_generated_at).total_seconds() / 3600, 0.0)

        latest_status = str(latest_entry.get("status") or "unknown")
        if latest_status == "failure":
            status = "failed"
            message = str(latest_entry.get("message") or "Latest saved report entry is a failure.")
        elif parsed_generated_at is None:
            status = "invalid-time"
            message = "Latest saved report entry is missing a parseable generated_at timestamp."
        elif age_hours is not None and age_hours > max_age_hours:
            status = "stale"
            message = f"Latest saved report entry is older than {max_age_hours:g}h."
        else:
            status = "ok"
            message = None

        health_entries.append(
            LiveSmokeReportHealthEntry(
                target=registry_target.key,
                status=status,
                generated_at=str(generated_at) if generated_at is not None else None,
                age_hours=age_hours,
                report_path=latest_entry.get("path"),
                report_type=str(latest_entry.get("report_type") or "") or None,
                selected_url=str(latest_entry.get("selected_url") or "") or None,
                used_fallback=bool(latest_entry.get("used_fallback")),
                message=message,
            )
        )

    scan_summary = get_live_smoke_report_scan_summary(directory, recursive=recursive)
    return health_entries, scan_summary


def resolve_latest_live_smoke_report(
    directory: Path,
    *,
    recursive: bool = True,
    report_type: str | None = None,
    target: str | None = None,
    used_fallback_only: bool = False,
    failed_only: bool = False,
) -> Path:
    normalized_type = _normalize_live_smoke_report_type(report_type)
    normalized_target = target.strip() if target else None
    reports, ignored = _scan_live_smoke_reports(directory, recursive=recursive)
    filtered_reports = [
        report
        for report in reports
        if (not normalized_type or report["type"] == normalized_type)
        and (not normalized_target or normalized_target in report.get("targets", []))
        and (not used_fallback_only or report.get("has_fallback"))
        and (not failed_only or report.get("has_failures"))
    ]
    filtered_reports.sort(
        key=lambda item: (
            str(item.get("generated_at") or ""),
            item["path"].as_posix(),
        ),
        reverse=True,
    )
    if not filtered_reports:
        filter_summary = describe_live_smoke_report_filters(
            report_type=normalized_type,
            target=normalized_target,
            used_fallback_only=used_fallback_only,
            failed_only=failed_only,
        )
        ignored_summary = summarize_ignored_live_smoke_reports(ignored)
        raise ValueError(
            f"No matching live smoke reports found in {directory.as_posix()} "
            f"| filters: {filter_summary} | recognized reports: {len(reports)} | {ignored_summary}"
        )
    return filtered_reports[0]["path"]


def resolve_latest_live_smoke_report_pair(
    directory: Path,
    *,
    recursive: bool = True,
    report_type: str | None = None,
    target: str | None = None,
    used_fallback_only: bool = False,
    failed_only: bool = False,
) -> tuple[Path, Path]:
    reports = list_live_smoke_reports(
        directory,
        recursive=recursive,
        report_type=report_type,
        target=target,
        latest=2,
        used_fallback_only=used_fallback_only,
        failed_only=failed_only,
    )
    if len(reports) >= 2:
        return reports[1]["path"], reports[0]["path"]

    scan_summary = get_live_smoke_report_scan_summary(directory, recursive=recursive)
    filter_summary = describe_live_smoke_report_filters(
        report_type=report_type,
        target=target,
        used_fallback_only=used_fallback_only,
        failed_only=failed_only,
    )
    ignored_summary = summarize_ignored_live_smoke_reports(scan_summary["ignored"])
    if not reports:
        raise ValueError(
            f"No matching live smoke reports found in {directory.as_posix()} "
            f"| filters: {filter_summary} | recognized reports: {scan_summary['recognized_count']} | {ignored_summary}"
        )
    raise ValueError(
        f"Need at least 2 matching live smoke reports in {directory.as_posix()} "
        f"| filters: {filter_summary} | recognized reports: {scan_summary['recognized_count']} | {ignored_summary}"
    )


def compare_live_smoke_reports(base_report_path: Path, current_report_path: Path) -> list[str]:
    base_payload = json.loads(base_report_path.read_text(encoding="utf-8"))
    current_payload = json.loads(current_report_path.read_text(encoding="utf-8"))
    base_entries = _live_smoke_report_entries(base_payload)
    current_entries = _live_smoke_report_entries(current_payload)

    base_keys = set(base_entries)
    current_keys = set(current_entries)
    added = sorted(current_keys - base_keys)
    removed = sorted(base_keys - current_keys)
    shared = sorted(base_keys & current_keys)

    changed: list[str] = []
    for key in shared:
        before = base_entries[key]
        after = current_entries[key]
        if before == after:
            continue
        if before.get("status") != after.get("status"):
            changed.append(f"CHANGED {key}: {before.get('status')} -> {after.get('status')}")
            continue
        if after.get("status") == "failure":
            changed.append(f"CHANGED {key}: failure message changed")
            continue

        before_mode = "fallback" if before.get("used_fallback") else "primary"
        after_mode = "fallback" if after.get("used_fallback") else "primary"
        changed.append(
            f"CHANGED {key}: {before.get('selected_url')} -> {after.get('selected_url')} "
            f"| {before_mode} -> {after_mode}"
        )

    lines = [
        f"Base report: {base_report_path.as_posix()}",
        f"Current report: {current_report_path.as_posix()}",
        f"Base entries: {len(base_entries)}",
        f"Current entries: {len(current_entries)}",
        f"Added targets: {len(added)}",
        f"Removed targets: {len(removed)}",
        f"Changed targets: {len(changed)}",
    ]

    for key in added:
        lines.append(f"ADDED {key}")
    for key in removed:
        lines.append(f"REMOVED {key}")
    lines.extend(changed)
    return lines


def summarize_live_smoke_report(report_path: Path) -> list[str]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    lines: list[str] = [f"Report: {report_path.as_posix()}"]

    if "successes" in payload and "failures" in payload:
        selected_targets = payload.get("selected_targets") or []
        lines.append("Type: batch")
        lines.append(f"Generated at: {payload.get('generated_at', 'unknown')}")
        lines.append(f"Selected targets: {', '.join(selected_targets) if selected_targets else 'all'}")
        lines.append(f"Success count: {payload.get('success_count', 0)}")
        lines.append(f"Failure count: {payload.get('failure_count', 0)}")
        for success in payload.get("successes", []):
            fallback = "fallback" if success.get("used_fallback") else "primary"
            label = success.get("candidate_label") or "-"
            lines.append(
                "SUCCESS "
                f"{success.get('target', '-')}: {success.get('selected_url', '-')} "
                f"| {fallback} | label={label}"
            )
        for failure in payload.get("failures", []):
            lines.append(f"FAILURE {failure.get('target', '-')}: {failure.get('message', '-')}")
        return lines

    if "selected_url" in payload:
        fallback = "fallback" if payload.get("used_fallback") else "primary"
        lines.append("Type: single")
        lines.append(f"Generated at: {payload.get('generated_at', 'unknown')}")
        lines.append(f"Target: {payload.get('target') or 'manual override'}")
        lines.append(f"Selected URL: {payload.get('selected_url', '-')}")
        lines.append(f"Selection: {fallback}")
        lines.append(f"Candidate label: {payload.get('candidate_label') or '-'}")
        lines.append(f"Cleaned: {payload.get('cleaned')}")
        return lines

    raise ValueError(f"Unrecognized live smoke report schema: {report_path.as_posix()}")


def write_live_smoke_report(
    artifacts: LiveResumeSmokeArtifacts,
    *,
    targets_path: Path,
    target_key: str | None,
    output_path: Path,
    overwrite: bool = False,
) -> Path:
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Live smoke report already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "targets_path": targets_path.as_posix(),
        "target": target_key,
        "selected_url": artifacts.selected_url,
        "candidate_label": artifacts.candidate_label,
        "used_fallback": artifacts.used_fallback,
        "cleaned": artifacts.cleaned,
        "run_dir": artifacts.run_dir.as_posix(),
        "job_path": artifacts.job_path.as_posix(),
        "report_path": artifacts.report_path.as_posix(),
        "tailoring_path": artifacts.tailoring_path.as_posix(),
        "tailored_context_path": artifacts.tailored_context_path.as_posix(),
        "html_path": artifacts.html_path.as_posix(),
        "pdf_path": artifacts.pdf_path.as_posix() if artifacts.pdf_path else None,
    }

    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_live_smoke_batch_report(
    result: BatchLiveResumeSmokeResult,
    *,
    targets_path: Path,
    selected_targets: list[str] | None,
    output_path: Path,
    overwrite: bool = False,
) -> Path:
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Live smoke batch report already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "targets_path": targets_path.as_posix(),
        "selected_targets": selected_targets or [],
        "success_count": len(result.successes),
        "failure_count": len(result.failures),
        "successes": [
            {
                "target": target_key,
                "selected_url": artifacts.selected_url,
                "candidate_label": artifacts.candidate_label,
                "used_fallback": artifacts.used_fallback,
                "cleaned": artifacts.cleaned,
                "run_dir": artifacts.run_dir.as_posix(),
                "job_path": artifacts.job_path.as_posix(),
                "report_path": artifacts.report_path.as_posix(),
                "tailoring_path": artifacts.tailoring_path.as_posix(),
                "tailored_context_path": artifacts.tailored_context_path.as_posix(),
                "html_path": artifacts.html_path.as_posix(),
                "pdf_path": artifacts.pdf_path.as_posix() if artifacts.pdf_path else None,
            }
            for target_key, artifacts in result.successes
        ],
        "failures": [
            {
                "target": target_key,
                "message": message,
            }
            for target_key, message in result.failures
        ],
    }

    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


__all__ = [
    "DEFAULT_LIVE_SMOKE_TARGETS_PATH",
    "compare_live_smoke_reports",
    "describe_live_smoke_report_filters",
    "evaluate_live_smoke_report_health",
    "get_live_smoke_report_scan_summary",
    "list_latest_live_smoke_entries_by_target",
    "list_live_smoke_reports",
    "list_live_smoke_targets",
    "live_smoke_report_metadata",
    "load_live_smoke_target",
    "resolve_latest_live_smoke_report",
    "resolve_latest_live_smoke_report_pair",
    "summarize_ignored_live_smoke_reports",
    "summarize_live_smoke_report",
    "write_live_smoke_batch_report",
    "write_live_smoke_report",
]

