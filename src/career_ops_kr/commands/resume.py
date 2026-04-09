from __future__ import annotations

import asyncio
import copy
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from career_ops_kr.jobs import fetch_job_to_markdown
from career_ops_kr.portals import canonicalize_job_url, infer_source_from_url
from career_ops_kr.scoring import ScoreJobArtifacts, score_job_file
from career_ops_kr.utils import ensure_dir, load_yaml, parse_front_matter, slugify, title_case


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIVE_SMOKE_TARGETS_PATH = REPO_ROOT / "config" / "live-smoke-targets.yml"
COMMON_ROLE_STOPWORDS = {
    "and",
    "backend",
    "data",
    "developer",
    "engineer",
    "engineering",
    "for",
    "platform",
    "senior",
    "software",
    "the",
    "with",
}


@dataclass(slots=True)
class ResumeTailoringArtifacts:
    output_path: Path
    packet: dict[str, Any]


@dataclass(slots=True)
class TailoredResumeContextArtifacts:
    output_path: Path
    context: dict[str, Any]


@dataclass(slots=True)
class BuildTailoredResumeArtifacts:
    tailoring_path: Path
    tailored_context_path: Path
    html_path: Path
    pdf_path: Path | None = None
    manifest_path: Path | None = None


@dataclass(slots=True)
class BuildTailoredResumeFromUrlArtifacts:
    job_path: Path
    report_path: Path
    tracker_path: Path | None
    tailoring_path: Path
    tailored_context_path: Path
    html_path: Path
    pdf_path: Path | None = None
    manifest_path: Path | None = None


@dataclass(slots=True)
class LiveResumeSmokeArtifacts:
    run_dir: Path
    job_path: Path
    report_path: Path
    tailoring_path: Path
    tailored_context_path: Path
    html_path: Path
    pdf_path: Path | None
    selected_url: str
    candidate_label: str | None
    used_fallback: bool
    cleaned: bool


@dataclass(slots=True)
class LiveResumeSmokeCandidate:
    url: str
    source: str | None = None
    label: str | None = None


@dataclass(slots=True)
class LiveResumeSmokeTarget:
    key: str
    candidates: list[LiveResumeSmokeCandidate]
    base_context_path: Path
    template_path: Path
    profile_path: Path
    description: str = ""


@dataclass(slots=True)
class BatchLiveResumeSmokeResult:
    successes: list[tuple[str, LiveResumeSmokeArtifacts]]
    failures: list[tuple[str, str]]


@dataclass(slots=True)
class LiveSmokeReportHealthEntry:
    target: str
    status: str
    generated_at: str | None
    age_hours: float | None
    report_path: Path | None
    report_type: str | None
    selected_url: str | None = None
    used_fallback: bool = False
    message: str | None = None


def _default_resume_artifact_manifest_path(html_path: Path) -> Path:
    return html_path.with_suffix(".manifest.json")


def _load_resume_guidance_from_context(context_path: Path) -> dict[str, Any] | None:
    if not context_path.exists():
        return None
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    guidance = payload.get("tailoringGuidance")
    return guidance if isinstance(guidance, dict) else None


def _load_resume_job_metadata(job_path: Path) -> dict[str, str | None]:
    try:
        front_matter, _ = parse_front_matter(job_path)
    except OSError:
        return {
            "company": None,
            "title": None,
            "url": None,
            "source": None,
        }
    return {
        "company": str(front_matter.get("company") or "").strip() or None,
        "title": str(front_matter.get("title") or "").strip() or None,
        "url": str(front_matter.get("url") or "").strip() or None,
        "source": str(front_matter.get("source") or "").strip() or None,
    }


def load_resume_artifact_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid artifact manifest payload: {path.as_posix()}")
    if payload.get("version") != 1:
        raise ValueError(f"Unsupported artifact manifest version: {path.as_posix()}")
    if not isinstance(payload.get("paths"), dict):
        raise ValueError(f"Artifact manifest is missing paths: {path.as_posix()}")
    return payload


def _write_resume_artifact_manifest(
    *,
    manifest_path: Path,
    pipeline: str,
    job_path: Path,
    report_path: Path,
    tailoring_path: Path,
    context_path: Path,
    html_path: Path,
    pdf_path: Path | None,
    base_context_path: Path,
    template_path: Path,
    scorecard_path: Path,
    profile_path: Path | None = None,
) -> Path:
    job = _load_resume_job_metadata(job_path)
    guidance = _load_resume_guidance_from_context(context_path) or {}
    payload = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "pipeline": pipeline,
        "job": job,
        "selection": guidance.get("selection") or {},
        "focus": guidance.get("focus") or {},
        "paths": {
            "job_path": job_path.as_posix(),
            "report_path": report_path.as_posix(),
            "tailoring_path": tailoring_path.as_posix(),
            "context_path": context_path.as_posix(),
            "html_path": html_path.as_posix(),
            "pdf_path": pdf_path.as_posix() if pdf_path else None,
            "base_context_path": base_context_path.as_posix(),
            "template_path": template_path.as_posix(),
            "profile_path": profile_path.as_posix() if profile_path else None,
            "scorecard_path": scorecard_path.as_posix(),
        },
    }
    ensure_dir(manifest_path.parent)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


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


def _scan_live_smoke_reports(directory: Path, *, recursive: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
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
    normalized_type = _normalize_live_smoke_report_type(report_type) if report_type is not None else None
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
            changed.append(
                f"CHANGED {key}: {before.get('status')} -> {after.get('status')}"
            )
            continue
        if after.get("status") == "failure":
            changed.append(
                f"CHANGED {key}: failure message changed"
            )
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
            lines.append(
                f"FAILURE {failure.get('target', '-')}: {failure.get('message', '-')}"
            )
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


def render_resume_html(template_path: Path, context_path: Path, output_path: Path) -> Path:
    context = json.loads(context_path.read_text(encoding="utf-8"))
    environment = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(template_path.name)
    html = template.render(**context)

    ensure_dir(output_path.parent)
    output_path.write_text(html, encoding="utf-8")
    return output_path


async def _generate_pdf_async(input_path: Path, output_path: Path, page_format: str) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        html = input_path.read_text(encoding="utf-8")
        await page.set_content(html, wait_until="networkidle")
        ensure_dir(output_path.parent)
        await page.pdf(
            path=output_path.as_posix(),
            format=page_format,
            print_background=True,
            margin={"top": "0.4in", "right": "0.4in", "bottom": "0.4in", "left": "0.4in"},
        )
        await browser.close()


def generate_pdf_file(input_path: Path, output_path: Path, page_format: str) -> Path:
    asyncio.run(_generate_pdf_async(input_path, output_path, page_format))
    return output_path


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        normalized = cleaned.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(cleaned)
    return unique


def _target_role_terms(value: str) -> list[str]:
    tokens = re.split(r"[^a-z0-9+#.-]+", value.lower())
    return [
        token
        for token in tokens
        if len(token) >= 3 and token not in COMMON_ROLE_STOPWORDS
    ]


def _parse_report_summary(report_text: str, report_path: Path) -> dict[str, str]:
    summary: dict[str, str] = {}
    for line in report_text.splitlines():
        if not line.startswith("- "):
            continue
        label, separator, value = line[2:].partition(":")
        if not separator:
            continue
        summary[label.strip()] = value.strip()

    required_labels = [
        "Selected Domain",
        "Selected Target Role",
        "Selected Role Profile",
        "Total Score",
        "Recommendation",
    ]
    missing = [label for label in required_labels if not summary.get(label)]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            f"Score report is missing required summary fields ({joined}): {report_path.as_posix()}"
        )
    return summary


def _extract_report_section_bullets(report_text: str, heading: str) -> list[str]:
    lines = report_text.splitlines()
    collected: list[str] = []
    in_section = False
    heading_line = f"## {heading}"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if stripped == heading_line:
                in_section = True
                continue
            if in_section:
                break
        if in_section and stripped.startswith("- "):
            collected.append(stripped[2:].strip())
    return collected


def _resolve_role_profile(
    selected_role_profile: str,
    scorecard: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    role_profiles = scorecard.get("role_profiles", {})
    normalized_target = _normalize_key(selected_role_profile)
    for key, profile in role_profiles.items():
        label = str(profile.get("label", ""))
        if _normalize_key(key) == normalized_target or _normalize_key(label) == normalized_target:
            return str(key), profile
    return None, {}


def _collect_profile_keywords(
    profile_key: str | None,
    role_profile: dict[str, Any],
    selected_target_role: str,
) -> list[str]:
    keywords = _unique_strings(
        [
            *(str(keyword) for keyword in role_profile.get("stack_keywords", [])),
            *(str(keyword) for keyword in role_profile.get("match_keywords", [])),
            *(str(keyword) for keyword in role_profile.get("specialization_keywords", [])),
            *(_target_role_terms(selected_target_role)),
        ]
    )

    if profile_key == "backend":
        keywords = [keyword for keyword in keywords if keyword.lower() not in {"backend"}]
    return keywords


def _matched_job_keywords(job_text: str, keywords: list[str], *, limit: int = 8) -> list[str]:
    matched = [keyword for keyword in keywords if keyword.lower() in job_text]
    return matched[:limit]


def _base_context_skills(base_context: dict[str, Any]) -> list[str]:
    return [str(skill) for skill in base_context.get("skills", [])]


def _matching_priority(value: str, keywords: list[str]) -> tuple[int, int]:
    lower = value.lower()
    matched = [keyword for keyword in keywords if keyword.lower() in lower]
    if not matched:
        return (0, 0)
    longest = max(len(keyword) for keyword in matched)
    return (len(matched), longest)


def _reorder_skills(existing_skills: list[str], emphasis_keywords: list[str]) -> list[str]:
    original = [str(skill) for skill in existing_skills]
    emphasized: list[str] = []
    remaining: list[str] = []
    for skill in original:
        if skill.lower() in {keyword.lower() for keyword in emphasis_keywords}:
            emphasized.append(skill)
        else:
            remaining.append(skill)
    return emphasized + remaining


def _entry_text(entry: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("role", "company", "period", "location", "name", "subtitle", "program", "school"):
        if key in entry and entry[key]:
            values.append(str(entry[key]))
    bullets = entry.get("bullets", [])
    if isinstance(bullets, list):
        values.extend(str(item) for item in bullets)
    return "\n".join(values)


def _sort_resume_entries(entries: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    indexed_entries = list(enumerate(entries))
    ranked = sorted(
        indexed_entries,
        key=lambda item: (
            _matching_priority(_entry_text(item[1]), keywords)[0],
            _matching_priority(_entry_text(item[1]), keywords)[1],
            -item[0],
        ),
        reverse=True,
    )
    return [entry for _, entry in ranked]


def _build_tailoring_summary(
    job_title: str,
    selected_role_profile: str,
    recommendation: str,
    matched_keywords: list[str],
) -> str:
    focus = ", ".join(matched_keywords[:3]) if matched_keywords else selected_role_profile
    return (
        f"Resume version for {job_title} with emphasis on {focus}. "
        f"Current score recommendation: {recommendation}."
    )


def _resume_artifact_slug(job_path: Path) -> tuple[str, str]:
    metadata, _body = parse_front_matter(job_path)
    company = title_case(str(metadata.get("company") or "Unknown"))
    title = title_case(str(metadata.get("title") or job_path.stem))
    return datetime.now(UTC).date().isoformat(), slugify(f"{company}-{title}", fallback="resume")


def _resume_url_artifact_slug(url: str, source: str) -> tuple[str, str]:
    normalized_url = canonicalize_job_url(url)
    parsed = httpx.URL(normalized_url)
    parts = [part for part in parsed.path.split("/") if part]
    path_hint = "-".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else parsed.host or "job")
    return datetime.now(UTC).date().isoformat(), slugify(f"{source}-{path_hint}", fallback="resume")


def _resume_smoke_run_dir(url: str, source: str) -> Path:
    normalized_url = canonicalize_job_url(url)
    parsed = httpx.URL(normalized_url)
    parts = [part for part in parsed.path.split("/") if part]
    path_hint = "-".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else parsed.host or "job")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = slugify(f"{source}-{path_hint}", fallback="resume-smoke")
    return Path("output") / "live-smoke" / f"{timestamp}-{slug}"


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
                        source=str(raw_candidate.get("source")).strip().lower() if raw_candidate.get("source") else None,
                        label=str(raw_candidate.get("label")).strip() if raw_candidate.get("label") else None,
                    )
                )
        if raw_url:
            candidates.insert(
                0,
                LiveResumeSmokeCandidate(
                    url=raw_url,
                    source=str(raw_target.get("source")).strip().lower() if raw_target.get("source") else None,
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
    raise ValueError(
        f"Unknown live smoke target '{target_key}'. Available targets: {available}"
    )


def create_resume_tailoring_packet(
    job_path: Path,
    report_path: Path,
    *,
    out: Path | None = None,
    base_context_path: Path | None = None,
    scorecard_path: Path = REPO_ROOT / "config" / "scorecard.kr.yml",
    overwrite: bool = False,
) -> ResumeTailoringArtifacts:
    if not job_path.exists():
        raise ValueError(f"Job markdown path does not exist: {job_path.as_posix()}")
    if not report_path.exists():
        raise ValueError(f"Score report path does not exist: {report_path.as_posix()}")
    if base_context_path and not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")
    if not scorecard_path.exists():
        raise ValueError(f"Scorecard path does not exist: {scorecard_path.as_posix()}")

    metadata, job_body = parse_front_matter(job_path)
    report_text = report_path.read_text(encoding="utf-8")
    summary = _parse_report_summary(report_text, report_path)
    scorecard = load_yaml(scorecard_path)

    job_title = title_case(str(metadata.get("title") or job_path.stem))
    company = title_case(str(metadata.get("company") or "Unknown"))
    if company == "Unknown":
        report_title = report_text.splitlines()[0].removeprefix("# ").strip() if report_text.strip() else ""
        if " - " in report_title:
            company = title_case(report_title.split(" - ", 1)[0])

    selected_domain = summary["Selected Domain"]
    selected_target_role = summary["Selected Target Role"]
    selected_role_profile = summary["Selected Role Profile"]
    recommendation = summary["Recommendation"]
    total_score_raw = summary["Total Score"].removesuffix("/5").strip()
    total_score = float(total_score_raw)
    language_signal = [
        value.strip()
        for value in summary.get("Language Signal", "ko").split(",")
        if value.strip()
    ]

    role_profile_key, role_profile = _resolve_role_profile(selected_role_profile, scorecard)
    profile_keywords = _collect_profile_keywords(role_profile_key, role_profile, selected_target_role)
    job_text = f"{job_title}\n{job_body}".lower()
    skills_to_emphasize = _matched_job_keywords(job_text, profile_keywords)

    base_context: dict[str, Any] = {}
    if base_context_path:
        base_context = json.loads(base_context_path.read_text(encoding="utf-8"))
    base_skills = _base_context_skills(base_context)
    base_context_text = json.dumps(base_context, ensure_ascii=False).lower() if base_context else ""
    matched_resume_skills = [
        skill for skill in base_skills if skill.lower() in job_text
    ]
    missing_focus_keywords = [
        keyword for keyword in skills_to_emphasize if keyword.lower() not in base_context_text
    ]

    why_it_fits = _extract_report_section_bullets(report_text, "Why It Fits")
    risks = _extract_report_section_bullets(report_text, "Risks")

    date = summary.get("Date") or datetime.now(UTC).date().isoformat()
    default_output = (
        Path("output")
        / "resume-tailoring"
        / f"{date}-{slugify(f'{company}-{job_title}', fallback='resume-tailoring')}.json"
    )
    output_path = out or default_output
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Resume tailoring packet already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )

    packet: dict[str, Any] = {
        "source": {
            "job_path": job_path.as_posix(),
            "report_path": report_path.as_posix(),
            "base_context_path": base_context_path.as_posix() if base_context_path else None,
            "scorecard_path": scorecard_path.as_posix(),
        },
        "job": {
            "company": company,
            "title": job_title,
            "url": metadata.get("url"),
            "source": metadata.get("source", "manual"),
        },
        "selection": {
            "selected_domain": selected_domain,
            "selected_target_role": selected_target_role,
            "selected_role_profile": selected_role_profile,
            "total_score": total_score,
            "recommendation": recommendation,
            "seniority_signal": summary.get("Seniority Signal", "mid"),
            "work_mode_signal": summary.get("Work Mode Signal", "unknown"),
            "language_signal": language_signal,
        },
        "tailoring": {
            "headline": selected_target_role if selected_target_role != "General" else job_title,
            "summary": _build_tailoring_summary(
                job_title,
                selected_role_profile,
                recommendation,
                skills_to_emphasize,
            ),
            "skills_to_emphasize": skills_to_emphasize,
            "matched_resume_skills": matched_resume_skills,
            "missing_focus_keywords": missing_focus_keywords,
            "experience_focus": [
                (
                    f"Move bullets proving {', '.join(skills_to_emphasize[:3])} closer to the top."
                    if skills_to_emphasize
                    else f"Move the most relevant {selected_role_profile} experience closer to the top."
                ),
                f"Make recent experience read like a direct match for {selected_target_role}.",
            ],
            "project_focus": [
                (
                    f"Highlight projects that show {', '.join(skills_to_emphasize[:2])} in production."
                    if len(skills_to_emphasize) >= 2
                    else f"Highlight one project that supports the {selected_target_role} narrative."
                ),
                f"Prefer {selected_domain} work that reduces perceived onboarding risk.",
            ],
            "keywords": skills_to_emphasize,
            "notes": [
                f"Recommendation from score report: {recommendation}",
                *[f"Fit signal: {line}" for line in why_it_fits[:2]],
                *[f"Risk check: {line}" for line in risks[:2]],
            ],
        },
    }

    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ResumeTailoringArtifacts(output_path=output_path, packet=packet)


def apply_resume_tailoring_packet(
    tailoring_path: Path,
    base_context_path: Path,
    *,
    out: Path | None = None,
    overwrite: bool = False,
) -> TailoredResumeContextArtifacts:
    if not tailoring_path.exists():
        raise ValueError(f"Resume tailoring packet does not exist: {tailoring_path.as_posix()}")
    if not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")

    packet = json.loads(tailoring_path.read_text(encoding="utf-8"))
    base_context = json.loads(base_context_path.read_text(encoding="utf-8"))

    tailoring = packet.get("tailoring")
    selection = packet.get("selection")
    job = packet.get("job")
    if not isinstance(tailoring, dict) or not isinstance(selection, dict) or not isinstance(job, dict):
        raise ValueError(f"Invalid resume tailoring packet schema: {tailoring_path.as_posix()}")

    for required_key in ("headline", "summary", "skills_to_emphasize", "experience_focus", "project_focus", "notes"):
        if required_key not in tailoring:
            raise ValueError(
                f"Resume tailoring packet is missing '{required_key}': {tailoring_path.as_posix()}"
            )

    company = title_case(str(job.get("company") or "Unknown"))
    title = title_case(str(job.get("title") or "Resume"))
    date = datetime.now(UTC).date().isoformat()
    default_output = (
        Path("output")
        / "resume-contexts"
        / f"{date}-{slugify(f'{company}-{title}', fallback='resume-context')}.json"
    )
    output_path = out or default_output
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Tailored resume context already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )

    tailored_context = copy.deepcopy(base_context)
    tailored_context["headline"] = str(tailoring["headline"])
    tailored_context["summary"] = str(tailoring["summary"])

    existing_skills = [str(skill) for skill in tailored_context.get("skills", [])]
    emphasis_keywords = [str(keyword) for keyword in tailoring.get("skills_to_emphasize", [])]
    ranking_keywords = _unique_strings(
        [
            *emphasis_keywords,
            *(str(keyword) for keyword in tailoring.get("keywords", [])),
            *(str(skill) for skill in tailoring.get("matched_resume_skills", [])),
            *(_target_role_terms(str(selection.get("selected_target_role", "")))),
        ]
    )

    if existing_skills:
        tailored_context["skills"] = _reorder_skills(existing_skills, emphasis_keywords)

    experience = tailored_context.get("experience")
    if isinstance(experience, list):
        tailored_context["experience"] = _sort_resume_entries(experience, ranking_keywords)

    projects = tailored_context.get("projects")
    if isinstance(projects, list):
        tailored_context["projects"] = _sort_resume_entries(projects, ranking_keywords)

    tailored_context["tailoringGuidance"] = {
        "tailoring_path": tailoring_path.as_posix(),
        "job": {
            "company": company,
            "title": title,
            "url": job.get("url"),
            "source": job.get("source"),
        },
        "selection": {
            "selected_domain": selection.get("selected_domain"),
            "selected_target_role": selection.get("selected_target_role"),
            "selected_role_profile": selection.get("selected_role_profile"),
            "total_score": selection.get("total_score"),
            "recommendation": selection.get("recommendation"),
        },
        "focus": {
            "skills_to_emphasize": emphasis_keywords,
            "missing_focus_keywords": [str(item) for item in tailoring.get("missing_focus_keywords", [])],
            "experience_focus": [str(item) for item in tailoring.get("experience_focus", [])],
            "project_focus": [str(item) for item in tailoring.get("project_focus", [])],
            "notes": [str(item) for item in tailoring.get("notes", [])],
        },
    }

    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(tailored_context, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return TailoredResumeContextArtifacts(output_path=output_path, context=tailored_context)


def build_tailored_resume(
    job_path: Path,
    report_path: Path,
    base_context_path: Path,
    template_path: Path,
    *,
    html_out: Path | None = None,
    tailoring_out: Path | None = None,
    tailored_context_out: Path | None = None,
    pdf_out: Path | None = None,
    scorecard_path: Path = REPO_ROOT / "config" / "scorecard.kr.yml",
    overwrite: bool = False,
    pdf_format: str = "A4",
) -> BuildTailoredResumeArtifacts:
    if not job_path.exists():
        raise ValueError(f"Job markdown path does not exist: {job_path.as_posix()}")
    if not report_path.exists():
        raise ValueError(f"Score report path does not exist: {report_path.as_posix()}")
    if not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")
    if not template_path.exists():
        raise ValueError(f"Resume template does not exist: {template_path.as_posix()}")

    date, slug = _resume_artifact_slug(job_path)
    resolved_tailoring_out = tailoring_out or Path("output") / "resume-tailoring" / f"{date}-{slug}.json"
    resolved_context_out = tailored_context_out or Path("output") / "resume-contexts" / f"{date}-{slug}.json"
    resolved_html_out = html_out or Path("output") / "rendered-resumes" / f"{date}-{slug}.html"
    resolved_manifest_out = _default_resume_artifact_manifest_path(resolved_html_out)

    protected_outputs = [
        resolved_tailoring_out,
        resolved_context_out,
        resolved_html_out,
        resolved_manifest_out,
    ]
    if pdf_out:
        protected_outputs.append(pdf_out)
    existing_outputs = [path for path in protected_outputs if path.exists()]
    if existing_outputs and not overwrite:
        joined = ", ".join(path.as_posix() for path in existing_outputs)
        raise ValueError(f"Resume build output already exists: {joined} | Use --overwrite to replace it.")

    tailoring = create_resume_tailoring_packet(
        job_path,
        report_path,
        out=resolved_tailoring_out,
        base_context_path=base_context_path,
        scorecard_path=scorecard_path,
        overwrite=overwrite,
    )
    tailored_context = apply_resume_tailoring_packet(
        tailoring.output_path,
        base_context_path,
        out=resolved_context_out,
        overwrite=overwrite,
    )
    render_resume_html(template_path, tailored_context.output_path, resolved_html_out)

    resolved_pdf_out: Path | None = None
    if pdf_out:
        resolved_pdf_out = generate_pdf_file(resolved_html_out, pdf_out, pdf_format)
    manifest_path = _write_resume_artifact_manifest(
        manifest_path=resolved_manifest_out,
        pipeline="build_tailored_resume",
        job_path=job_path,
        report_path=report_path,
        tailoring_path=tailoring.output_path,
        context_path=tailored_context.output_path,
        html_path=resolved_html_out,
        pdf_path=resolved_pdf_out,
        base_context_path=base_context_path,
        template_path=template_path,
        scorecard_path=scorecard_path,
    )

    return BuildTailoredResumeArtifacts(
        tailoring_path=tailoring.output_path,
        tailored_context_path=tailored_context.output_path,
        html_path=resolved_html_out,
        pdf_path=resolved_pdf_out,
        manifest_path=manifest_path,
    )


def build_tailored_resume_from_url(
    url: str,
    base_context_path: Path,
    template_path: Path,
    *,
    source: str | None = None,
    job_out: Path | None = None,
    report_out: Path | None = None,
    tracker_out: Path | None = None,
    html_out: Path | None = None,
    tailoring_out: Path | None = None,
    tailored_context_out: Path | None = None,
    pdf_out: Path | None = None,
    profile_path: Path = REPO_ROOT / "config" / "profile.yml",
    scorecard_path: Path = REPO_ROOT / "config" / "scorecard.kr.yml",
    overwrite: bool = False,
    insecure: bool = False,
    pdf_format: str = "A4",
    fetch_job_func: Any | None = None,
    score_job_func: Any | None = None,
    build_tailored_resume_func: Any | None = None,
    infer_source_func: Any | None = None,
) -> BuildTailoredResumeFromUrlArtifacts:
    if not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")
    if not template_path.exists():
        raise ValueError(f"Resume template does not exist: {template_path.as_posix()}")
    if not profile_path.exists():
        raise ValueError(f"Profile path does not exist: {profile_path.as_posix()}")
    if not scorecard_path.exists():
        raise ValueError(f"Scorecard path does not exist: {scorecard_path.as_posix()}")

    infer_source = infer_source_func or infer_source_from_url
    resolved_source = (source or infer_source(url)).strip().lower() or "manual"
    date, slug = _resume_url_artifact_slug(url, resolved_source)
    resolved_job_out = job_out or Path("jds") / f"{date}-{slug}.md"
    resolved_report_out = report_out or Path("reports") / f"{date}-{slug}.md"
    resolved_tailoring_out = tailoring_out or Path("output") / "resume-tailoring" / f"{date}-{slug}.json"
    resolved_context_out = tailored_context_out or Path("output") / "resume-contexts" / f"{date}-{slug}.json"
    resolved_html_out = html_out or Path("output") / "rendered-resumes" / f"{date}-{slug}.html"
    resolved_manifest_out = _default_resume_artifact_manifest_path(resolved_html_out)

    protected_outputs = [
        resolved_job_out,
        resolved_report_out,
        resolved_tailoring_out,
        resolved_context_out,
        resolved_html_out,
        resolved_manifest_out,
    ]
    if tracker_out:
        protected_outputs.append(tracker_out)
    if pdf_out:
        protected_outputs.append(pdf_out)
    existing_outputs = [path for path in protected_outputs if path.exists()]
    if existing_outputs and not overwrite:
        joined = ", ".join(path.as_posix() for path in existing_outputs)
        raise ValueError(
            f"Resume-from-url output already exists: {joined} | Use --overwrite to replace it."
        )

    fetch_job = fetch_job_func or fetch_job_to_markdown
    score_job = score_job_func or score_job_file
    build_resume = build_tailored_resume_func or build_tailored_resume

    saved_job_path = fetch_job(
        url,
        out=resolved_job_out,
        source=resolved_source,
        insecure=insecure,
    )
    score_artifacts: ScoreJobArtifacts = score_job(
        saved_job_path,
        report_path=resolved_report_out,
        tracker_path=tracker_out,
        profile_path=profile_path,
        scorecard_path=scorecard_path,
        write_tracker=tracker_out is not None,
    )
    resume_artifacts: BuildTailoredResumeArtifacts = build_resume(
        saved_job_path,
        score_artifacts.report_path,
        base_context_path,
        template_path,
        html_out=resolved_html_out,
        tailoring_out=resolved_tailoring_out,
        tailored_context_out=resolved_context_out,
        pdf_out=pdf_out,
        scorecard_path=scorecard_path,
        overwrite=overwrite,
        pdf_format=pdf_format,
    )
    manifest_path = _write_resume_artifact_manifest(
        manifest_path=resume_artifacts.manifest_path
        or _default_resume_artifact_manifest_path(resume_artifacts.html_path),
        pipeline="build_tailored_resume_from_url",
        job_path=saved_job_path,
        report_path=score_artifacts.report_path,
        tailoring_path=resume_artifacts.tailoring_path,
        context_path=resume_artifacts.tailored_context_path,
        html_path=resume_artifacts.html_path,
        pdf_path=resume_artifacts.pdf_path,
        base_context_path=base_context_path,
        template_path=template_path,
        scorecard_path=scorecard_path,
        profile_path=profile_path,
    )

    return BuildTailoredResumeFromUrlArtifacts(
        job_path=saved_job_path,
        report_path=score_artifacts.report_path,
        tracker_path=score_artifacts.tracker_path,
        tailoring_path=resume_artifacts.tailoring_path,
        tailored_context_path=resume_artifacts.tailored_context_path,
        html_path=resume_artifacts.html_path,
        pdf_path=resume_artifacts.pdf_path,
        manifest_path=manifest_path,
    )


def run_live_resume_smoke(
    *,
    url: str | None = None,
    base_context_path: Path | None = None,
    template_path: Path | None = None,
    profile_path: Path | None = None,
    scorecard_path: Path,
    source: str | None = None,
    target_key: str | None = None,
    targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    out_dir: Path | None = None,
    insecure: bool = False,
    keep_artifacts: bool = False,
    overwrite: bool = False,
    pdf: bool = False,
    pdf_format: str = "A4",
    build_from_url_func: Any | None = None,
) -> LiveResumeSmokeArtifacts:
    selected_target: LiveResumeSmokeTarget | None = None
    if target_key:
        selected_target = load_live_smoke_target(target_key, targets_path)

    override_url = url.strip() if url else ""
    target_candidates = selected_target.candidates if selected_target else []
    candidate_pool = (
        [LiveResumeSmokeCandidate(url=override_url, source=source, label="override")]
        if override_url
        else target_candidates
    )
    if not candidate_pool:
        raise ValueError("Live smoke requires a URL or a named target.")

    resolved_base_context = base_context_path or (selected_target.base_context_path if selected_target else None)
    resolved_template = template_path or (selected_target.template_path if selected_target else None)
    resolved_profile = profile_path or (selected_target.profile_path if selected_target else None)
    if resolved_base_context is None:
        raise ValueError("Live smoke requires a base resume context path.")
    if resolved_template is None:
        raise ValueError("Live smoke requires a template path.")
    if resolved_profile is None:
        raise ValueError("Live smoke requires a profile path.")

    build_from_url = build_from_url_func or build_tailored_resume_from_url
    failures: list[str] = []
    selected_url = ""
    selected_label: str | None = None
    used_fallback = False
    artifacts: BuildTailoredResumeFromUrlArtifacts | None = None
    run_dir: Path | None = None

    for candidate_index, candidate in enumerate(candidate_pool):
        candidate_url = candidate.url.strip()
        candidate_source = (
            (source or candidate.source or infer_source_from_url(candidate_url)).strip().lower() or "manual"
        )
        candidate_run_dir = out_dir or _resume_smoke_run_dir(candidate_url, candidate_source)
        if candidate_run_dir.exists() and not overwrite:
            raise ValueError(
                f"Live smoke output directory already exists: {candidate_run_dir.as_posix()} | Use --overwrite to replace it."
            )
        try:
            artifacts = build_from_url(
                candidate_url,
                resolved_base_context,
                resolved_template,
                source=candidate_source,
                job_out=candidate_run_dir / "job.md",
                report_out=candidate_run_dir / "report.md",
                html_out=candidate_run_dir / "resume.html",
                tailoring_out=candidate_run_dir / "tailoring.json",
                tailored_context_out=candidate_run_dir / "context.json",
                pdf_out=(candidate_run_dir / "resume.pdf") if pdf else None,
                profile_path=resolved_profile,
                scorecard_path=scorecard_path,
                overwrite=overwrite,
                insecure=insecure,
                pdf_format=pdf_format,
            )
        except ValueError as exc:
            failures.append(f"{candidate_url} -> {exc}")
            continue

        selected_url = candidate_url
        selected_label = candidate.label
        used_fallback = candidate_index > 0
        run_dir = candidate_run_dir
        break

    if artifacts is None or run_dir is None:
        attempted = "; ".join(failures) if failures else "no candidates attempted"
        raise ValueError(f"Live smoke failed for target '{target_key or 'manual'}': {attempted}")

    required_paths = [
        artifacts.job_path,
        artifacts.report_path,
        artifacts.tailoring_path,
        artifacts.tailored_context_path,
        artifacts.html_path,
    ]
    for path in required_paths:
        if not path.exists():
            raise ValueError(f"Live smoke did not produce expected artifact: {path.as_posix()}")
    if pdf and not artifacts.pdf_path:
        raise ValueError("Live smoke requested PDF output but no PDF artifact was returned.")
    if artifacts.pdf_path and not artifacts.pdf_path.exists():
        raise ValueError(f"Live smoke did not produce expected PDF artifact: {artifacts.pdf_path.as_posix()}")

    cleaned = False
    if not keep_artifacts:
        shutil.rmtree(run_dir, ignore_errors=False)
        cleaned = True

    return LiveResumeSmokeArtifacts(
        run_dir=run_dir,
        job_path=artifacts.job_path,
        report_path=artifacts.report_path,
        tailoring_path=artifacts.tailoring_path,
        tailored_context_path=artifacts.tailored_context_path,
        html_path=artifacts.html_path,
        pdf_path=artifacts.pdf_path,
        selected_url=selected_url,
        candidate_label=selected_label,
        used_fallback=used_fallback,
        cleaned=cleaned,
    )


def run_batch_live_resume_smoke(
    *,
    target_keys: list[str] | None,
    targets_path: Path = DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    scorecard_path: Path,
    out_root: Path | None = None,
    insecure: bool = False,
    keep_artifacts: bool = False,
    overwrite: bool = False,
    pdf: bool = False,
    pdf_format: str = "A4",
    continue_on_error: bool = True,
    run_live_smoke_func: Any | None = None,
) -> BatchLiveResumeSmokeResult:
    available_targets = list_live_smoke_targets(targets_path)
    selected_keys = target_keys or [target.key for target in available_targets]
    selected_targets = [load_live_smoke_target(key, targets_path) for key in selected_keys]

    run_live_smoke = run_live_smoke_func or run_live_resume_smoke
    successes: list[tuple[str, LiveResumeSmokeArtifacts]] = []
    failures: list[tuple[str, str]] = []

    for target in selected_targets:
        try:
            artifacts = run_live_smoke(
                target_key=target.key,
                targets_path=targets_path,
                scorecard_path=scorecard_path,
                out_dir=(out_root / target.key) if out_root else None,
                insecure=insecure,
                keep_artifacts=keep_artifacts,
                overwrite=overwrite,
                pdf=pdf,
                pdf_format=pdf_format,
            )
        except ValueError as exc:
            failures.append((target.key, str(exc)))
            if not continue_on_error:
                break
            continue
        successes.append((target.key, artifacts))

    return BatchLiveResumeSmokeResult(successes=successes, failures=failures)
