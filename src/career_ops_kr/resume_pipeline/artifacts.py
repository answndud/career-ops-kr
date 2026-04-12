from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from career_ops_kr.resume_pipeline.models import BackfillArtifactManifestResult
from career_ops_kr.utils import ensure_dir, parse_front_matter


ARTIFACT_INDEX_FILENAME = "artifact-index.json"


@dataclass(frozen=True, slots=True)
class ArtifactInventoryFinding:
    category: str
    severity: str
    message: str
    path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
        }


@dataclass(slots=True)
class ArtifactInventoryAuditResult:
    html_artifact_count: int
    manifest_count: int
    legacy_html_count: int
    findings: list[ArtifactInventoryFinding]

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
            "html_artifact_count": self.html_artifact_count,
            "manifest_count": self.manifest_count,
            "legacy_html_count": self.legacy_html_count,
            "finding_count": len(self.findings),
            "counts": self.counts,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _default_resume_artifact_manifest_path(html_path: Path) -> Path:
    return html_path.with_suffix(".manifest.json")


def _artifact_output_root_for_path(html_path: Path) -> Path:
    resolved_html_path = html_path.resolve()
    for candidate in (resolved_html_path.parent, *resolved_html_path.parents):
        if candidate.name == "output":
            return candidate
    return resolved_html_path.parent


def _artifact_index_path_for_output_root(output_root: Path) -> Path:
    return output_root / ARTIFACT_INDEX_FILENAME


def _artifact_inventory_key(html_path: Path, *, output_root: Path | None = None) -> str:
    resolved_html_path = html_path.resolve()
    resolved_output_root = output_root or _artifact_output_root_for_path(resolved_html_path)
    try:
        return resolved_html_path.relative_to(resolved_output_root.resolve()).as_posix()
    except ValueError:
        return resolved_html_path.as_posix()


def _new_build_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"br_{timestamp}_{uuid4().hex[:8]}"


def _legacy_backfill_build_run_id(html_path: Path, *, generated_at: str) -> str:
    digest = hashlib.sha1(
        f"{html_path.resolve().as_posix()}|{generated_at}".encode("utf-8")
    ).hexdigest()[:12]
    return f"backfill_{digest}"


def _default_artifact_index_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "entries": {},
    }


def _load_artifact_index_payload(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return _default_artifact_index_payload()
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid artifact index payload: {index_path.as_posix()}")
    if payload.get("version") != 1:
        raise ValueError(f"Unsupported artifact index version: {index_path.as_posix()}")
    if not isinstance(payload.get("entries"), dict):
        raise ValueError(f"Artifact index is missing entries: {index_path.as_posix()}")
    return payload


def _upsert_artifact_index_entry_from_manifest(manifest_path: Path) -> Path:
    output_root, inventory_key, entry = _artifact_index_entry_from_manifest(manifest_path)
    index_path = _artifact_index_path_for_output_root(output_root)
    try:
        payload = _load_artifact_index_payload(index_path)
    except (ValueError, json.JSONDecodeError, OSError):
        payload = _default_artifact_index_payload()
    payload["entries"][inventory_key] = entry
    payload["updated_at"] = datetime.now(UTC).isoformat()
    ensure_dir(index_path.parent)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return index_path


def _artifact_index_entry_from_manifest(manifest_path: Path) -> tuple[Path, str, dict[str, Any]]:
    manifest = load_resume_artifact_manifest(manifest_path)
    manifest_paths = manifest.get("paths") or {}
    if not isinstance(manifest_paths, dict):
        raise ValueError(f"Artifact manifest is missing paths: {manifest_path.as_posix()}")
    html_path_value = manifest_paths.get("html_path")
    if not isinstance(html_path_value, str) or not html_path_value.strip():
        raise ValueError(f"Artifact manifest is missing html_path: {manifest_path.as_posix()}")

    html_path = Path(html_path_value)
    output_root = _artifact_output_root_for_path(html_path)
    inventory_key = str(
        manifest.get("inventory_key")
        or _artifact_inventory_key(html_path, output_root=output_root)
    )
    entry = {
        "inventory_key": inventory_key,
        "build_run_id": manifest.get("build_run_id"),
        "generated_at": manifest.get("generated_at"),
        "pipeline": manifest.get("pipeline"),
        "manifest_path": manifest_path.as_posix(),
        "html_path": html_path.as_posix(),
        "pdf_path": manifest_paths.get("pdf_path"),
    }
    return output_root, inventory_key, entry


def _rebuild_artifact_index(output_root: Path) -> int:
    index_path = _artifact_index_path_for_output_root(output_root)
    previous_keys: set[str] = set()
    try:
        previous_payload = _load_artifact_index_payload(index_path)
        previous_keys = {
            key for key in previous_payload.get("entries", {}).keys() if isinstance(key, str)
        }
    except (ValueError, json.JSONDecodeError, OSError):
        previous_keys = set()

    entries: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted(output_root.rglob("*.manifest.json")):
        if not manifest_path.is_file():
            continue
        try:
            manifest_output_root, inventory_key, entry = _artifact_index_entry_from_manifest(manifest_path)
        except (ValueError, json.JSONDecodeError, OSError):
            continue
        if manifest_output_root.resolve() != output_root.resolve():
            continue
        html_path = Path(str(entry["html_path"]))
        if not html_path.exists():
            continue
        entries[inventory_key] = entry

    pruned_count = len(previous_keys - set(entries))
    if not entries:
        if index_path.exists():
            index_path.unlink()
        return pruned_count

    payload = _default_artifact_index_payload()
    payload["entries"] = entries
    payload["updated_at"] = datetime.now(UTC).isoformat()
    ensure_dir(index_path.parent)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return pruned_count


def _load_resume_guidance_from_context(context_path: Path) -> dict[str, Any] | None:
    if not context_path.exists():
        return None
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    guidance = payload.get("tailoringGuidance")
    return guidance if isinstance(guidance, dict) else None


def _job_metadata_from_guidance(guidance: dict[str, Any] | None) -> dict[str, str | None]:
    if not isinstance(guidance, dict):
        return {
            "company": None,
            "title": None,
            "url": None,
            "source": None,
        }
    job = guidance.get("job")
    if not isinstance(job, dict):
        return {
            "company": None,
            "title": None,
            "url": None,
            "source": None,
        }
    return {
        "company": str(job.get("company") or "").strip() or None,
        "title": str(job.get("title") or "").strip() or None,
        "url": str(job.get("url") or "").strip() or None,
        "source": str(job.get("source") or "").strip() or None,
    }


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
    job_path: Path | None,
    report_path: Path | None,
    tailoring_path: Path | None,
    context_path: Path | None,
    html_path: Path,
    pdf_path: Path | None,
    base_context_path: Path | None,
    template_path: Path | None,
    scorecard_path: Path | None,
    profile_path: Path | None = None,
    generated_at: str | None = None,
    build_run_id: str | None = None,
    inventory_key: str | None = None,
) -> Path:
    guidance = _load_resume_guidance_from_context(context_path) if context_path else None
    normalized_guidance = guidance or {}
    job = (
        _load_resume_job_metadata(job_path)
        if job_path and job_path.exists()
        else _job_metadata_from_guidance(guidance)
    )
    output_root = _artifact_output_root_for_path(html_path)
    resolved_inventory_key = inventory_key or _artifact_inventory_key(
        html_path, output_root=output_root
    )
    payload = {
        "version": 1,
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "build_run_id": build_run_id or _new_build_run_id(),
        "inventory_key": resolved_inventory_key,
        "pipeline": pipeline,
        "job": job,
        "selection": normalized_guidance.get("selection") or {},
        "focus": normalized_guidance.get("focus") or {},
        "paths": {
            "job_path": job_path.as_posix() if job_path else None,
            "report_path": report_path.as_posix() if report_path else None,
            "tailoring_path": tailoring_path.as_posix() if tailoring_path else None,
            "context_path": context_path.as_posix() if context_path else None,
            "html_path": html_path.as_posix(),
            "pdf_path": pdf_path.as_posix() if pdf_path else None,
            "base_context_path": base_context_path.as_posix() if base_context_path else None,
            "template_path": template_path.as_posix() if template_path else None,
            "profile_path": profile_path.as_posix() if profile_path else None,
            "scorecard_path": scorecard_path.as_posix() if scorecard_path else None,
        },
    }
    ensure_dir(manifest_path.parent)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _upsert_artifact_index_entry_from_manifest(manifest_path)
    return manifest_path


def backfill_artifact_manifests(
    *,
    output_dir: Path,
    jd_dir: Path,
    report_dir: Path,
    overwrite: bool = False,
    dry_run: bool = False,
) -> BackfillArtifactManifestResult:
    if not output_dir.exists():
        return BackfillArtifactManifestResult(
            scanned=0,
            created=0,
            overwritten=0,
            skipped=0,
            manifests=[],
            pruned_index_entries=0,
        )

    html_paths = sorted(
        [path for path in output_dir.rglob("*.html") if path.is_file()],
        key=lambda path: path.as_posix(),
    )
    manifests: list[Path] = []
    created = 0
    overwritten_count = 0
    skipped = 0
    context_root = output_dir / "resume-contexts"
    tailoring_root = output_dir / "resume-tailoring"

    for html_path in html_paths:
        manifest_path = _default_resume_artifact_manifest_path(html_path)
        existed_before = manifest_path.exists()
        if existed_before and not overwrite:
            if not dry_run:
                try:
                    _upsert_artifact_index_entry_from_manifest(manifest_path)
                except (ValueError, json.JSONDecodeError, OSError):
                    pass
            skipped += 1
            continue

        pdf_path = html_path.with_suffix(".pdf")
        resolved_pdf_path = pdf_path if pdf_path.exists() else None
        job_path = jd_dir / f"{html_path.stem}.md"
        report_path = report_dir / f"{html_path.stem}.md"
        context_path = context_root / f"{html_path.stem}.json"
        tailoring_path = tailoring_root / f"{html_path.stem}.json"

        resolved_job_path = job_path if job_path.exists() else None
        resolved_report_path = report_path if report_path.exists() else None
        resolved_context_path = context_path if context_path.exists() else None
        resolved_tailoring_path = tailoring_path if tailoring_path.exists() else None
        generated_at = datetime.fromtimestamp(html_path.stat().st_mtime, UTC).isoformat()
        build_run_id = _legacy_backfill_build_run_id(html_path, generated_at=generated_at)

        manifests.append(manifest_path)
        if dry_run:
            if existed_before:
                overwritten_count += 1
            else:
                created += 1
            continue

        _write_resume_artifact_manifest(
            manifest_path=manifest_path,
            pipeline="legacy_backfill",
            job_path=resolved_job_path,
            report_path=resolved_report_path,
            tailoring_path=resolved_tailoring_path,
            context_path=resolved_context_path,
            html_path=html_path,
            pdf_path=resolved_pdf_path,
            base_context_path=None,
            template_path=None,
            scorecard_path=None,
            profile_path=None,
            generated_at=generated_at,
            build_run_id=build_run_id,
        )
        if existed_before:
            overwritten_count += 1
        else:
            created += 1

    pruned_index_entries = 0
    if not dry_run:
        pruned_index_entries = _rebuild_artifact_index(output_dir)

    return BackfillArtifactManifestResult(
        scanned=len(html_paths),
        created=created,
        overwritten=overwritten_count,
        skipped=skipped,
        manifests=manifests,
        pruned_index_entries=pruned_index_entries,
    )


def _resolve_artifact_audit_path(value: Any, *, repo_root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    if path.is_absolute():
        return path
    return repo_root / path


def _load_artifact_index_entries_for_audit(
    index_path: Path,
    *,
    findings: list[ArtifactInventoryFinding],
) -> dict[str, dict[str, Any]]:
    try:
        payload = _load_artifact_index_payload(index_path)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        findings.append(
            ArtifactInventoryFinding(
                category="invalid_artifact_index",
                severity="error",
                message=f"Artifact index could not be parsed: {exc}",
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
            ArtifactInventoryFinding(
                category="invalid_artifact_index",
                severity="error",
                message="Artifact index contains malformed entries.",
                path=index_path.as_posix(),
            )
        )
    return normalized_entries


def _load_artifact_manifest_for_audit(
    manifest_path: Path,
    *,
    findings: list[ArtifactInventoryFinding],
) -> dict[str, Any] | None:
    try:
        return load_resume_artifact_manifest(manifest_path)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        findings.append(
            ArtifactInventoryFinding(
                category="invalid_manifest",
                severity="error",
                message=f"Artifact manifest could not be parsed: {exc}",
                path=manifest_path.as_posix(),
            )
        )
        return None


def _append_manifest_referenced_path_findings_for_audit(
    manifest_payload_paths: dict[str, Any],
    *,
    repo_root: Path,
    findings: list[ArtifactInventoryFinding],
) -> None:
    for field_name, category, label in (
        ("job_path", "manifest_missing_job_file", "job"),
        ("report_path", "manifest_missing_report_file", "report"),
        ("tailoring_path", "manifest_missing_tailoring_file", "tailoring"),
        ("context_path", "manifest_missing_context_file", "context"),
        ("pdf_path", "manifest_missing_pdf_file", "pdf"),
    ):
        resolved = _resolve_artifact_audit_path(manifest_payload_paths.get(field_name), repo_root=repo_root)
        if resolved is None or resolved.exists():
            continue
        findings.append(
            ArtifactInventoryFinding(
                category=category,
                severity="error",
                message=f"Artifact manifest points to a {label} file that does not exist.",
                path=resolved.as_posix(),
            )
        )


def _artifact_audit_paths_match(path_value: Any, expected_path: Path, *, repo_root: Path) -> bool:
    resolved = _resolve_artifact_audit_path(path_value, repo_root=repo_root)
    if resolved is None:
        return False
    return resolved.resolve() == expected_path.resolve()


def audit_artifact_inventory(
    *,
    output_dir: Path,
    repo_root: Path = Path("."),
) -> ArtifactInventoryAuditResult:
    resolved_repo_root = Path(repo_root)
    resolved_output_dir = Path(output_dir)
    if not resolved_output_dir.is_absolute():
        resolved_output_dir = resolved_repo_root / resolved_output_dir
    if not resolved_output_dir.exists():
        return ArtifactInventoryAuditResult(
            html_artifact_count=0,
            manifest_count=0,
            legacy_html_count=0,
            findings=[],
        )

    findings: list[ArtifactInventoryFinding] = []
    html_paths = sorted(path for path in resolved_output_dir.rglob("*.html") if path.is_file())
    manifest_paths = sorted(path for path in resolved_output_dir.rglob("*.manifest.json") if path.is_file())
    legacy_html_paths = [html_path for html_path in html_paths if not html_path.with_suffix(".manifest.json").exists()]

    index_path = resolved_output_dir / ARTIFACT_INDEX_FILENAME
    index_entries: dict[str, dict[str, Any]] = {}
    if manifest_paths and not index_path.exists():
        findings.append(
            ArtifactInventoryFinding(
                category="missing_artifact_index",
                severity="warn",
                message="Output root has manifest files but artifact-index.json is missing.",
                path=index_path.as_posix(),
            )
        )
    elif index_path.exists():
        index_entries = _load_artifact_index_entries_for_audit(index_path, findings=findings)

    seen_inventory_keys: set[str] = set()
    for manifest_path in manifest_paths:
        manifest = _load_artifact_manifest_for_audit(manifest_path, findings=findings)
        if manifest is None:
            continue
        manifest_payload_paths = manifest.get("paths") or {}
        if not isinstance(manifest_payload_paths, dict):
            continue

        html_path = _resolve_artifact_audit_path(
            manifest_payload_paths.get("html_path"),
            repo_root=resolved_repo_root,
        )
        if html_path is None:
            findings.append(
                ArtifactInventoryFinding(
                    category="invalid_manifest",
                    severity="error",
                    message="Artifact manifest is missing html_path.",
                    path=manifest_path.as_posix(),
                )
            )
            continue
        if not html_path.exists():
            findings.append(
                ArtifactInventoryFinding(
                    category="manifest_missing_html_file",
                    severity="error",
                    message="Artifact manifest points to an HTML file that does not exist.",
                    path=html_path.as_posix(),
                )
            )
            continue

        _append_manifest_referenced_path_findings_for_audit(
            manifest_payload_paths,
            repo_root=resolved_repo_root,
            findings=findings,
        )

        inventory_key = str(manifest.get("inventory_key") or "").strip() or _artifact_inventory_key(
            html_path,
            output_root=resolved_output_dir,
        )
        seen_inventory_keys.add(inventory_key)

        if index_entries:
            entry = index_entries.get(inventory_key)
            if entry is None:
                findings.append(
                    ArtifactInventoryFinding(
                        category="missing_artifact_index_entry",
                        severity="warn",
                        message="Artifact manifest is missing a matching artifact-index entry.",
                        path=manifest_path.as_posix(),
                    )
                )
            else:
                mismatched_fields: list[str] = []
                if not _artifact_audit_paths_match(
                    entry.get("manifest_path"),
                    manifest_path,
                    repo_root=resolved_repo_root,
                ):
                    mismatched_fields.append("manifest_path")
                if not _artifact_audit_paths_match(
                    entry.get("html_path"),
                    html_path,
                    repo_root=resolved_repo_root,
                ):
                    mismatched_fields.append("html_path")
                if mismatched_fields:
                    findings.append(
                        ArtifactInventoryFinding(
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
                    ArtifactInventoryFinding(
                        category="invalid_artifact_index",
                        severity="error",
                        message="Artifact-index entry is not an object.",
                        path=index_path.as_posix(),
                    )
                )
                continue
            referenced_manifest = _resolve_artifact_audit_path(
                entry.get("manifest_path"),
                repo_root=resolved_repo_root,
            )
            referenced_html = _resolve_artifact_audit_path(
                entry.get("html_path"),
                repo_root=resolved_repo_root,
            )
            manifest_exists = referenced_manifest is not None and referenced_manifest.exists()
            html_exists = referenced_html is not None and referenced_html.exists()
            if manifest_exists and html_exists:
                continue
            findings.append(
                ArtifactInventoryFinding(
                    category="orphan_artifact_index_entry",
                    severity="warn",
                    message="Artifact-index entry points to missing manifest or HTML artifact.",
                    path=index_path.as_posix(),
                )
            )

    for html_path in legacy_html_paths:
        findings.append(
            ArtifactInventoryFinding(
                category="legacy_html",
                severity="warn",
                message="HTML artifact is missing sibling manifest metadata.",
                path=html_path.as_posix(),
            )
        )

    return ArtifactInventoryAuditResult(
        html_artifact_count=len(html_paths),
        manifest_count=len(manifest_paths),
        legacy_html_count=len(legacy_html_paths),
        findings=findings,
    )


__all__ = [
    "ARTIFACT_INDEX_FILENAME",
    "ArtifactInventoryAuditResult",
    "ArtifactInventoryFinding",
    "_default_resume_artifact_manifest_path",
    "_new_build_run_id",
    "_write_resume_artifact_manifest",
    "audit_artifact_inventory",
    "backfill_artifact_manifests",
    "load_resume_artifact_manifest",
]
