from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_ops_kr.commands.resume import load_resume_artifact_manifest
from career_ops_kr.utils import slugify
from career_ops_kr.web.common import coerce_path, safe_relative_to, safe_text
from career_ops_kr.web.db import connection_scope
from career_ops_kr.web.paths import WebPaths


def output_url(path: Path, *, paths: WebPaths) -> str:
    try:
        relative = path.resolve().relative_to(paths.output_dir.resolve())
    except ValueError:
        return path.as_posix()
    return f"/output/{relative.as_posix()}"


def artifact_slug(company: str, position: str, role_key: str, language: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    basis = f"{company}-{position}-{role_key}-{language}"
    return f"{timestamp}-{slugify(basis, fallback='web-resume')}"


def artifact_manifest_sort_key(manifest_path: Path, *, paths: WebPaths) -> float:
    manifest = load_artifact_manifest(manifest_path, paths=paths)
    if manifest is not None:
        generated_at = safe_text(manifest.get("generated_at"))
        if generated_at:
            try:
                normalized = generated_at.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized).timestamp()
            except ValueError:
                pass
        manifest_paths_payload = manifest.get("paths") or {}
        if isinstance(manifest_paths_payload, dict):
            html_path = coerce_path(manifest_paths_payload.get("html_path"), repo_root=paths.repo_root)
            if html_path is not None and html_path.exists():
                return html_path.stat().st_mtime
    return manifest_path.stat().st_mtime


def artifact_inventory_key_for_html(html_path: Path, *, paths: WebPaths) -> str:
    try:
        return html_path.resolve().relative_to(paths.output_dir.resolve()).as_posix()
    except ValueError:
        return html_path.resolve().as_posix()


def artifact_index_path(*, paths: WebPaths) -> Path:
    return paths.output_dir / "artifact-index.json"


def load_artifact_index(*, paths: WebPaths) -> dict[str, Any] | None:
    index_path = artifact_index_path(paths=paths)
    if not index_path.exists():
        return None
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != 1:
        return None
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return None
    return payload


def filter_generated_resume_items(
    items: list[dict[str, Any]],
    *,
    source: str = "all",
    query: str = "",
) -> list[dict[str, Any]]:
    normalized_source = source.strip().lower()
    normalized_query = query.strip().lower()
    filtered: list[dict[str, Any]] = []
    for item in items:
        if normalized_source in {"web", "cli"} and item.get("source_label") != normalized_source:
            continue
        if normalized_query:
            haystack = " ".join(
                [
                    str(item.get("label") or ""),
                    str(item.get("company") or ""),
                    str(item.get("position") or ""),
                    str(item.get("html_path") or ""),
                    str(item.get("job_path") or ""),
                    str(item.get("report_path") or ""),
                    str(item.get("manifest_path") or ""),
                    str(item.get("build_pipeline") or ""),
                ]
            ).lower()
            if normalized_query not in haystack:
                continue
        filtered.append(item)
    return filtered


def load_tailoring_guidance(context_path: Path | None, *, paths: WebPaths) -> dict[str, Any] | None:
    if context_path is None or not context_path.exists():
        return None
    if not safe_relative_to(context_path, paths.output_dir / "resume-contexts"):
        return None
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    guidance = payload.get("tailoringGuidance")
    return guidance if isinstance(guidance, dict) else None


def build_focus_preview(guidance: dict[str, Any] | None) -> dict[str, list[str]]:
    if not guidance:
        return {"skills": [], "experience": [], "notes": []}
    focus = guidance.get("focus")
    if not isinstance(focus, dict):
        return {"skills": [], "experience": [], "notes": []}
    return {
        "skills": [str(item) for item in (focus.get("skills_to_emphasize") or [])[:4]],
        "experience": [str(item) for item in (focus.get("experience_focus") or [])[:3]],
        "notes": [str(item) for item in (focus.get("notes") or [])[:3]],
    }


def artifact_manifest_path_for_html(html_path: Path | None) -> Path | None:
    if html_path is None:
        return None
    manifest_path = html_path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        return None
    return manifest_path


def load_artifact_manifest(path: Path | None, *, paths: WebPaths) -> dict[str, Any] | None:
    if path is None or not path.exists() or not safe_relative_to(path, paths.output_dir):
        return None
    try:
        return load_resume_artifact_manifest(path)
    except (ValueError, json.JSONDecodeError, OSError):
        return None


def guidance_from_artifact_manifest(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manifest:
        return None
    selection = manifest.get("selection")
    focus = manifest.get("focus")
    normalized_selection = selection if isinstance(selection, dict) else {}
    normalized_focus = focus if isinstance(focus, dict) else {}
    if not normalized_selection and not normalized_focus:
        return None
    return {
        "selection": normalized_selection,
        "focus": normalized_focus,
    }


def generated_resume_snapshot(*, paths: WebPaths, limit: int | None = 6) -> dict[str, Any]:
    if not paths.output_dir.exists():
        return {"total": 0, "items": []}

    linked_rows_by_path: dict[str, dict[str, Any]] = {}
    with connection_scope() as conn:
        job_rows = conn.execute(
            """
            SELECT id, company, position, job_path, report_path, context_path, html_path, pdf_path
            FROM jobs
            WHERE job_path IS NOT NULL OR report_path IS NOT NULL OR context_path IS NOT NULL
               OR html_path IS NOT NULL OR pdf_path IS NOT NULL
            """
        ).fetchall()
    for row in job_rows:
        for field in ("job_path", "report_path", "context_path", "html_path", "pdf_path"):
            path = coerce_path(row.get(field), repo_root=paths.repo_root)
            if path is None:
                continue
            linked_rows_by_path[path.resolve().as_posix()] = row

    items: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    cli_total = 0
    web_total = 0
    manifest_total = 0
    legacy_total = 0
    artifact_index = load_artifact_index(paths=paths) or {}
    artifact_index_entries = (
        artifact_index.get("entries") if isinstance(artifact_index.get("entries"), dict) else {}
    )

    manifest_paths = sorted(
        [path for path in paths.output_dir.rglob("*.manifest.json") if path.is_file()],
        key=lambda path: artifact_manifest_sort_key(path, paths=paths),
        reverse=True,
    )
    for manifest_path in manifest_paths:
        manifest = load_artifact_manifest(manifest_path, paths=paths)
        if manifest is None:
            continue
        manifest_paths_payload = manifest.get("paths") or {}
        if not isinstance(manifest_paths_payload, dict):
            continue
        html_path = coerce_path(manifest_paths_payload.get("html_path"), repo_root=paths.repo_root)
        if html_path is None or not html_path.exists() or not safe_relative_to(html_path, paths.output_dir):
            continue
        resolved_html = html_path.resolve().as_posix()
        if resolved_html in seen_paths:
            continue
        seen_paths.add(resolved_html)

        pdf_path = coerce_path(manifest_paths_payload.get("pdf_path"), repo_root=paths.repo_root)
        report_path = coerce_path(manifest_paths_payload.get("report_path"), repo_root=paths.repo_root)
        job_path = coerce_path(manifest_paths_payload.get("job_path"), repo_root=paths.repo_root)
        context_path = coerce_path(manifest_paths_payload.get("context_path"), repo_root=paths.repo_root)
        linked_row = None
        for candidate_path in (html_path, pdf_path, job_path, report_path, context_path):
            if candidate_path is None:
                continue
            linked_row = linked_rows_by_path.get(candidate_path.resolve().as_posix())
            if linked_row is not None:
                break

        source_label = "web" if safe_relative_to(html_path, paths.web_resume_output_dir) else "cli"
        if source_label == "web":
            web_total += 1
        else:
            cli_total += 1
        manifest_total += 1

        guidance = guidance_from_artifact_manifest(manifest) or load_tailoring_guidance(
            context_path,
            paths=paths,
        )
        modified_at = datetime.fromtimestamp(html_path.stat().st_mtime, UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        manifest_job = manifest.get("job") if isinstance(manifest.get("job"), dict) else {}
        selection = manifest.get("selection") if isinstance(manifest.get("selection"), dict) else {}
        index_entry = artifact_index_entries.get(artifact_inventory_key_for_html(html_path, paths=paths))
        if not isinstance(index_entry, dict):
            index_entry = None
        items.append(
            {
                "label": html_path.name,
                "source_label": source_label,
                "provenance": "manifest",
                "provenance_label": "manifest",
                "build_pipeline": safe_text(manifest.get("pipeline")),
                "build_run_id": safe_text(manifest.get("build_run_id"))
                or safe_text((index_entry or {}).get("build_run_id")),
                "inventory_key": safe_text(manifest.get("inventory_key"))
                or safe_text((index_entry or {}).get("inventory_key"))
                or artifact_inventory_key_for_html(html_path, paths=paths),
                "manifest_path": manifest_path.as_posix(),
                "manifest_url": output_url(manifest_path, paths=paths),
                "html_path": html_path.as_posix(),
                "html_url": output_url(html_path, paths=paths),
                "pdf_path": pdf_path.as_posix() if pdf_path and pdf_path.exists() else None,
                "pdf_url": output_url(pdf_path, paths=paths) if pdf_path and pdf_path.exists() else None,
                "job_path": job_path.as_posix() if job_path and job_path.exists() else None,
                "report_path": report_path.as_posix() if report_path and report_path.exists() else None,
                "context_path": context_path.as_posix() if context_path and context_path.exists() else None,
                "job_id": int(linked_row["id"]) if linked_row else None,
                "job_detail_url": f"/tracker/{int(linked_row['id'])}" if linked_row else None,
                "company": safe_text(linked_row.get("company")) if linked_row else safe_text(manifest_job.get("company")),
                "position": safe_text(linked_row.get("position")) if linked_row else safe_text(manifest_job.get("title")),
                "guidance": guidance,
                "focus_preview": build_focus_preview(guidance),
                "modified_at": modified_at,
                "selected_role_profile": safe_text(selection.get("selected_role_profile")),
            }
        )

    html_paths = sorted(
        [path for path in paths.output_dir.rglob("*.html") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for html_path in html_paths:
        resolved_html = html_path.resolve().as_posix()
        if resolved_html in seen_paths:
            continue
        seen_paths.add(resolved_html)
        pdf_path = html_path.with_suffix(".pdf")
        derived_job_path = paths.jd_dir / f"{html_path.stem}.md"
        derived_report_path = paths.report_dir / f"{html_path.stem}.md"
        derived_context_path = paths.output_dir / "resume-contexts" / f"{html_path.stem}.json"
        linked_row = linked_rows_by_path.get(resolved_html)
        if linked_row is None and pdf_path.exists():
            linked_row = linked_rows_by_path.get(pdf_path.resolve().as_posix())
        job_path = coerce_path(linked_row.get("job_path"), repo_root=paths.repo_root) if linked_row else None
        report_path = coerce_path(linked_row.get("report_path"), repo_root=paths.repo_root) if linked_row else None
        context_path = coerce_path(linked_row.get("context_path"), repo_root=paths.repo_root) if linked_row else None
        if job_path is None:
            job_path = derived_job_path
        if report_path is None:
            report_path = derived_report_path
        if context_path is None:
            context_path = derived_context_path
        source_label = "web" if safe_relative_to(html_path, paths.web_resume_output_dir) else "cli"
        if source_label == "web":
            web_total += 1
        else:
            cli_total += 1
        legacy_total += 1
        guidance = load_tailoring_guidance(context_path, paths=paths)
        modified_at = datetime.fromtimestamp(html_path.stat().st_mtime, UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        items.append(
            {
                "label": html_path.name,
                "source_label": source_label,
                "provenance": "legacy",
                "provenance_label": "legacy",
                "build_pipeline": "",
                "build_run_id": None,
                "inventory_key": artifact_inventory_key_for_html(html_path, paths=paths),
                "manifest_path": None,
                "manifest_url": None,
                "html_path": html_path.as_posix(),
                "html_url": output_url(html_path, paths=paths),
                "pdf_path": pdf_path.as_posix() if pdf_path.exists() else None,
                "pdf_url": output_url(pdf_path, paths=paths) if pdf_path.exists() else None,
                "job_path": job_path.as_posix() if job_path.exists() else None,
                "report_path": report_path.as_posix() if report_path.exists() else None,
                "context_path": context_path.as_posix() if context_path.exists() else None,
                "job_id": int(linked_row["id"]) if linked_row else None,
                "job_detail_url": f"/tracker/{int(linked_row['id'])}" if linked_row else None,
                "company": safe_text(linked_row.get("company")) if linked_row else "",
                "position": safe_text(linked_row.get("position")) if linked_row else "",
                "guidance": guidance,
                "focus_preview": build_focus_preview(guidance),
                "modified_at": modified_at,
            }
        )
    return {
        "total": len(items),
        "web_total": web_total,
        "cli_total": cli_total,
        "manifest_total": manifest_total,
        "legacy_total": legacy_total,
        "items": items[:limit] if limit is not None else items,
    }
