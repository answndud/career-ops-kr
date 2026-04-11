from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from career_ops_kr.commands.resume import ARTIFACT_INDEX_FILENAME, load_resume_artifact_manifest
from career_ops_kr.utils import ensure_dir, load_yaml


ACTIVE_AUDIT_STATUSES = {
    "검토중",
    "지원예정",
    "지원완료",
    "서류통과",
    "과제",
    "1차면접",
    "2차면접",
    "최종면접",
    "오퍼",
    "보류",
}


@dataclass(frozen=True, slots=True)
class TrackerAuditFinding:
    category: str
    severity: str
    message: str
    tracker_id: str | None = None
    company: str = ""
    role: str = ""
    path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "tracker_id": self.tracker_id,
            "company": self.company,
            "role": self.role,
            "path": self.path,
        }


@dataclass(slots=True)
class TrackerAuditResult:
    tracker_row_count: int
    findings: list[TrackerAuditFinding]

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category] = counts.get(finding.category, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracker_row_count": self.tracker_row_count,
            "finding_count": len(self.findings),
            "counts": self.counts,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def normalize_status(status: str, states: dict[str, Any]) -> str:
    normalized = status.strip()
    if normalized in states["canonical"]:
        return normalized
    return states["aliases"].get(normalized.lower(), "검토중")


def parse_tracker_rows(content: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in content.splitlines():
        if not line.startswith("|") or "---" in line or "Company" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 10:
            continue
        rows.append(
            {
                "id": cells[0],
                "date": cells[1],
                "company": cells[2],
                "role": cells[3],
                "score": cells[4],
                "status": cells[5],
                "source": cells[6],
                "resume": cells[7],
                "report": cells[8],
                "notes": cells[9],
            }
        )
    return rows


def render_tracker(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Applications Tracker",
        "",
        "| ID | Date | Company | Role | Score | Status | Source | Resume | Report | Notes |",
        "|----|------|---------|------|-------|--------|--------|--------|--------|-------|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['date']} | {row['company']} | {row['role']} | "
            f"{row['score']} | {row['status']} | {row['source']} | {row['resume']} | "
            f"{row['report']} | {row['notes']} |"
        )
    lines.append("")
    return "\n".join(lines)


def merge_tracker_additions(
    tracker_path: str | Path,
    additions_dir: str | Path,
    *,
    states_path: str | Path = "config/states.yml",
    recursive: bool = False,
) -> int:
    states = load_yaml(states_path)
    tracker = Path(tracker_path)
    additions = Path(additions_dir)
    ensure_dir(tracker.parent)
    if not tracker.exists():
        tracker.write_text(render_tracker([]), encoding="utf-8")

    rows = parse_tracker_rows(tracker.read_text(encoding="utf-8"))
    max_id = max((int(row["id"]) for row in rows), default=0)
    keyed = {(row["company"], row["role"]): row for row in rows}
    addition_paths = list(_iter_addition_paths(additions, recursive=recursive))

    for addition_path in addition_paths:
        parts = addition_path.read_text(encoding="utf-8").strip().split("\t")
        if len(parts) < 9:
            continue
        date, company, role, score, status, source, resume, report, notes = parts[:9]
        key = (company, role)
        if key in keyed:
            row = keyed[key]
            row["date"] = date or row["date"]
            row["score"] = score or row["score"]
            row["status"] = normalize_status(status or row["status"], states)
            row["source"] = source or row["source"]
            row["resume"] = resume or row["resume"]
            row["report"] = report or row["report"]
            row["notes"] = notes or row["notes"]
        else:
            max_id += 1
            row = {
                "id": str(max_id),
                "date": date,
                "company": company,
                "role": role,
                "score": score,
                "status": normalize_status(status, states),
                "source": source,
                "resume": resume,
                "report": report,
                "notes": notes,
            }
            rows.append(row)
            keyed[key] = row

    rows.sort(key=lambda row: int(row["id"]))
    tracker.write_text(render_tracker(rows), encoding="utf-8")
    return len(addition_paths)


def normalize_tracker_statuses(
    tracker_path: str | Path,
    *,
    states_path: str | Path = "config/states.yml",
) -> int:
    states = load_yaml(states_path)
    tracker = Path(tracker_path)
    ensure_dir(tracker.parent)
    if not tracker.exists():
        tracker.write_text(render_tracker([]), encoding="utf-8")

    rows = parse_tracker_rows(tracker.read_text(encoding="utf-8"))
    changed = 0
    for row in rows:
        normalized = normalize_status(row["status"], states)
        if normalized != row["status"]:
            row["status"] = normalized
            changed += 1
    tracker.write_text(render_tracker(rows), encoding="utf-8")
    return changed


def save_tracker_row(
    tracker_path: str | Path,
    row_input: dict[str, str],
    *,
    states_path: str | Path = "config/states.yml",
) -> dict[str, str]:
    states = load_yaml(states_path)
    tracker = Path(tracker_path)
    ensure_dir(tracker.parent)
    if not tracker.exists():
        tracker.write_text(render_tracker([]), encoding="utf-8")

    rows = parse_tracker_rows(tracker.read_text(encoding="utf-8"))
    row_id = row_input.get("id", "").strip()
    target_row: dict[str, str] | None = None
    if row_id:
        target_row = next((row for row in rows if row["id"] == row_id), None)

    if target_row is None:
        next_id = max((int(row["id"]) for row in rows), default=0) + 1
        target_row = {
            "id": str(next_id),
            "date": "",
            "company": "",
            "role": "",
            "score": "",
            "status": "검토중",
            "source": "",
            "resume": "",
            "report": "",
            "notes": "",
        }
        rows.append(target_row)

    for key in ["date", "company", "role", "score", "source", "resume", "report", "notes"]:
        if key in row_input:
            target_row[key] = row_input[key].strip()
    if "status" in row_input:
        target_row["status"] = normalize_status(row_input["status"], states)

    rows.sort(key=lambda row: int(row["id"]))
    tracker.write_text(render_tracker(rows), encoding="utf-8")
    return target_row.copy()


def upsert_tracker_row(
    tracker_path: str | Path,
    row_input: dict[str, str],
    *,
    states_path: str | Path = "config/states.yml",
) -> dict[str, str]:
    states = load_yaml(states_path)
    tracker = Path(tracker_path)
    ensure_dir(tracker.parent)
    if not tracker.exists():
        tracker.write_text(render_tracker([]), encoding="utf-8")

    rows = parse_tracker_rows(tracker.read_text(encoding="utf-8"))
    row_id = row_input.get("id", "").strip()
    target_row: dict[str, str] | None = None
    if row_id:
        target_row = next((row for row in rows if row["id"] == row_id), None)

    if target_row is None:
        company = row_input.get("company", "").strip()
        role = row_input.get("role", "").strip()
        if company and role:
            target_row = next(
                (row for row in rows if row["company"] == company and row["role"] == role),
                None,
            )

    if target_row is None:
        return save_tracker_row(tracker, row_input, states_path=states_path)

    for key in ["date", "company", "role", "score", "source", "resume", "report", "notes"]:
        if key in row_input:
            target_row[key] = row_input[key].strip()
    if "status" in row_input:
        target_row["status"] = normalize_status(row_input["status"], states)

    rows.sort(key=lambda row: int(row["id"]))
    tracker.write_text(render_tracker(rows), encoding="utf-8")
    return target_row.copy()


def delete_tracker_row(
    tracker_path: str | Path,
    row_id: str | int,
) -> bool:
    tracker = Path(tracker_path)
    ensure_dir(tracker.parent)
    if not tracker.exists():
        tracker.write_text(render_tracker([]), encoding="utf-8")
        return False

    target_id = str(row_id).strip()
    rows = parse_tracker_rows(tracker.read_text(encoding="utf-8"))
    next_rows = [row for row in rows if row["id"] != target_id]
    if len(next_rows) == len(rows):
        return False
    tracker.write_text(render_tracker(next_rows), encoding="utf-8")
    return True


def audit_tracker_jobs(
    tracker_path: str | Path,
    *,
    repo_root: str | Path = ".",
    output_dir: str | Path = "output",
) -> TrackerAuditResult:
    tracker = Path(tracker_path)
    resolved_repo_root = Path(repo_root)
    findings: list[TrackerAuditFinding] = []
    if not tracker.exists():
        findings.append(
            TrackerAuditFinding(
                category="missing_tracker",
                severity="error",
                message="Tracker file does not exist.",
                path=tracker.as_posix(),
            )
        )
        return TrackerAuditResult(tracker_row_count=0, findings=findings)

    rows = parse_tracker_rows(tracker.read_text(encoding="utf-8"))
    for row in rows:
        tracker_id = row.get("id") or None
        company = row.get("company", "")
        role = row.get("role", "")
        report_path_value = row.get("report", "").strip()
        if not report_path_value:
            findings.append(
                TrackerAuditFinding(
                    category="missing_report",
                    severity="warn",
                    message="Tracker row has no report path.",
                    tracker_id=tracker_id,
                    company=company,
                    role=role,
                )
            )
        else:
            report_path = _resolve_tracker_artifact_path(report_path_value, repo_root=resolved_repo_root)
            if not report_path.exists():
                findings.append(
                    TrackerAuditFinding(
                        category="missing_report_file",
                        severity="error",
                        message="Tracker row points to a report file that does not exist.",
                        tracker_id=tracker_id,
                        company=company,
                        role=role,
                        path=report_path.as_posix(),
                    )
                )

        resume_path_value = row.get("resume", "").strip()
        if not resume_path_value:
            if row.get("status", "").strip() in ACTIVE_AUDIT_STATUSES:
                findings.append(
                    TrackerAuditFinding(
                        category="missing_resume",
                        severity="warn",
                        message="Active tracker row has no resume artifact path.",
                        tracker_id=tracker_id,
                        company=company,
                        role=role,
                    )
                )
        else:
            resume_path = _resolve_tracker_artifact_path(resume_path_value, repo_root=resolved_repo_root)
            if not resume_path.exists():
                findings.append(
                    TrackerAuditFinding(
                        category="missing_resume_file",
                        severity="error",
                        message="Tracker row points to a resume artifact that does not exist.",
                        tracker_id=tracker_id,
                        company=company,
                        role=role,
                        path=resume_path.as_posix(),
                    )
                )

    resolved_output_dir = Path(output_dir)
    if not resolved_output_dir.is_absolute():
        resolved_output_dir = resolved_repo_root / resolved_output_dir
    if resolved_output_dir.exists():
        manifest_paths = sorted(
            path for path in resolved_output_dir.rglob("*.manifest.json") if path.is_file()
        )
        index_path = resolved_output_dir / ARTIFACT_INDEX_FILENAME
        index_entries: dict[str, dict[str, Any]] = {}
        if manifest_paths and not index_path.exists():
            findings.append(
                TrackerAuditFinding(
                    category="missing_artifact_index",
                    severity="warn",
                    message="Output root has manifest files but artifact-index.json is missing.",
                    path=index_path.as_posix(),
                )
            )
        elif index_path.exists():
            index_entries = _load_artifact_index_entries(index_path, findings=findings)

        seen_inventory_keys: set[str] = set()
        for manifest_path in manifest_paths:
            manifest = _load_artifact_manifest_for_audit(manifest_path, findings=findings)
            if manifest is None:
                continue
            manifest_payload_paths = manifest.get("paths") or {}
            if not isinstance(manifest_payload_paths, dict):
                continue
            html_path_value = str(manifest_payload_paths.get("html_path") or "").strip()
            if not html_path_value:
                findings.append(
                    TrackerAuditFinding(
                        category="invalid_manifest",
                        severity="error",
                        message="Artifact manifest is missing html_path.",
                        path=manifest_path.as_posix(),
                    )
                )
                continue
            html_path = _resolve_tracker_artifact_path(html_path_value, repo_root=resolved_repo_root)
            if not html_path.exists():
                findings.append(
                    TrackerAuditFinding(
                        category="manifest_missing_html_file",
                        severity="error",
                        message="Artifact manifest points to an HTML file that does not exist.",
                        path=html_path.as_posix(),
                    )
                )
                continue
            _append_manifest_referenced_path_findings(
                manifest_payload_paths,
                repo_root=resolved_repo_root,
                findings=findings,
            )
            inventory_key = str(manifest.get("inventory_key") or "").strip() or _artifact_inventory_key_for_html(
                html_path,
                output_root=resolved_output_dir,
            )
            seen_inventory_keys.add(inventory_key)
            if index_entries:
                entry = index_entries.get(inventory_key)
                if entry is None:
                    findings.append(
                        TrackerAuditFinding(
                            category="missing_artifact_index_entry",
                            severity="warn",
                            message="Artifact manifest is missing a matching artifact-index entry.",
                            path=manifest_path.as_posix(),
                        )
                    )
                else:
                    mismatched_fields: list[str] = []
                    if not _paths_match(entry.get("manifest_path"), manifest_path, repo_root=resolved_repo_root):
                        mismatched_fields.append("manifest_path")
                    if not _paths_match(entry.get("html_path"), html_path, repo_root=resolved_repo_root):
                        mismatched_fields.append("html_path")
                    if mismatched_fields:
                        findings.append(
                            TrackerAuditFinding(
                                category="artifact_index_entry_mismatch",
                                severity="warn",
                                message="Artifact-index entry does not match manifest metadata: "
                                + ", ".join(mismatched_fields),
                                path=manifest_path.as_posix(),
                            )
                        )

        if index_entries:
            for inventory_key, entry in sorted(index_entries.items()):
                if inventory_key in seen_inventory_keys:
                    continue
                if not isinstance(entry, dict):
                    findings.append(
                        TrackerAuditFinding(
                            category="invalid_artifact_index",
                            severity="error",
                            message="Artifact-index entry is not an object.",
                            path=index_path.as_posix(),
                        )
                    )
                    continue
                referenced_manifest = _resolve_optional_artifact_path(
                    entry.get("manifest_path"),
                    repo_root=resolved_repo_root,
                )
                referenced_html = _resolve_optional_artifact_path(
                    entry.get("html_path"),
                    repo_root=resolved_repo_root,
                )
                manifest_exists = referenced_manifest is not None and referenced_manifest.exists()
                html_exists = referenced_html is not None and referenced_html.exists()
                if manifest_exists and html_exists:
                    continue
                findings.append(
                    TrackerAuditFinding(
                        category="orphan_artifact_index_entry",
                        severity="warn",
                        message="Artifact-index entry points to missing manifest or HTML artifact.",
                        path=index_path.as_posix(),
                    )
                )

        for html_path in sorted(path for path in resolved_output_dir.rglob("*.html") if path.is_file()):
            manifest_path = html_path.with_suffix(".manifest.json")
            if manifest_path.exists():
                continue
            findings.append(
                TrackerAuditFinding(
                    category="legacy_html",
                    severity="warn",
                    message="HTML artifact is missing sibling manifest metadata.",
                    path=html_path.as_posix(),
                )
            )

    return TrackerAuditResult(tracker_row_count=len(rows), findings=findings)


def _iter_addition_paths(additions_dir: Path, *, recursive: bool) -> list[Path]:
    if not additions_dir.exists():
        return []
    if recursive:
        return sorted(path for path in additions_dir.rglob("*.tsv") if path.is_file())
    return sorted(path for path in additions_dir.glob("*.tsv") if path.is_file())


def _resolve_tracker_artifact_path(value: str, *, repo_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def _resolve_optional_artifact_path(value: Any, *, repo_root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _resolve_tracker_artifact_path(value.strip(), repo_root=repo_root)


def _artifact_inventory_key_for_html(html_path: Path, *, output_root: Path) -> str:
    try:
        return html_path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError:
        return html_path.resolve().as_posix()


def _load_artifact_manifest_for_audit(
    manifest_path: Path,
    *,
    findings: list[TrackerAuditFinding],
) -> dict[str, Any] | None:
    try:
        return load_resume_artifact_manifest(manifest_path)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        findings.append(
            TrackerAuditFinding(
                category="invalid_manifest",
                severity="error",
                message=f"Artifact manifest could not be parsed: {exc}",
                path=manifest_path.as_posix(),
            )
        )
        return None


def _load_artifact_index_entries(
    index_path: Path,
    *,
    findings: list[TrackerAuditFinding],
) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        findings.append(
            TrackerAuditFinding(
                category="invalid_artifact_index",
                severity="error",
                message=f"Artifact index could not be parsed: {exc}",
                path=index_path.as_posix(),
            )
        )
        return {}
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("entries"), dict):
        findings.append(
            TrackerAuditFinding(
                category="invalid_artifact_index",
                severity="error",
                message="Artifact index has an unsupported schema.",
                path=index_path.as_posix(),
            )
        )
        return {}
    normalized_entries: dict[str, dict[str, Any]] = {}
    for inventory_key, entry in payload["entries"].items():
        if isinstance(inventory_key, str) and isinstance(entry, dict):
            normalized_entries[inventory_key] = entry
    if len(normalized_entries) != len(payload["entries"]):
        findings.append(
            TrackerAuditFinding(
                category="invalid_artifact_index",
                severity="error",
                message="Artifact index contains malformed entries.",
                path=index_path.as_posix(),
            )
        )
    return normalized_entries


def _append_manifest_referenced_path_findings(
    manifest_payload_paths: dict[str, Any],
    *,
    repo_root: Path,
    findings: list[TrackerAuditFinding],
) -> None:
    for field_name, category, label in (
        ("job_path", "manifest_missing_job_file", "job"),
        ("report_path", "manifest_missing_report_file", "report"),
        ("tailoring_path", "manifest_missing_tailoring_file", "tailoring"),
        ("context_path", "manifest_missing_context_file", "context"),
        ("pdf_path", "manifest_missing_pdf_file", "pdf"),
    ):
        resolved = _resolve_optional_artifact_path(manifest_payload_paths.get(field_name), repo_root=repo_root)
        if resolved is None or resolved.exists():
            continue
        findings.append(
            TrackerAuditFinding(
                category=category,
                severity="error",
                message=f"Artifact manifest points to a {label} file that does not exist.",
                path=resolved.as_posix(),
            )
        )


def _paths_match(path_value: Any, expected_path: Path, *, repo_root: Path) -> bool:
    resolved = _resolve_optional_artifact_path(path_value, repo_root=repo_root)
    if resolved is None:
        return False
    return resolved.resolve() == expected_path.resolve()
