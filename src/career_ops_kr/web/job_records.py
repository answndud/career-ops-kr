from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException


def normalize_web_source(
    source: str | None,
    url: str,
    *,
    safe_text: Callable[[Any], str],
) -> str | None:
    normalized = safe_text(source).lower()
    if normalized in {"원티드", "wanted"}:
        return "wanted"
    if normalized in {"사람인", "saramin"}:
        return "saramin"
    if normalized in {"리멤버", "remember"}:
        return "remember"
    if normalized in {"점핏", "jumpit"}:
        return "jumpit"
    if normalized == "efinancial":
        return None
    if "wanted.co.kr" in url:
        return "wanted"
    if "saramin.co.kr" in url:
        return "saramin"
    if "rememberapp.co.kr" in url:
        return "remember"
    if "jumpit.saramin.co.kr" in url or "jumpit" in url:
        return "jumpit"
    return None


def normalize_job_payload(
    payload: dict[str, Any],
    *,
    normalize_job_url: Callable[[Any], str | None],
    safe_text: Callable[[Any], str],
    safe_int: Callable[[Any], int | None],
    safe_bool: Callable[[Any], bool],
    default_status: str = "검토중",
) -> dict[str, Any]:
    company = safe_text(payload.get("company"))
    position = safe_text(payload.get("position") or payload.get("title"))
    if not company or not position:
        raise ValueError("Company and position are required")
    canonical_url = normalize_job_url(payload.get("url"))
    return {
        "company": company,
        "position": position,
        "url": canonical_url,
        "canonical_url": canonical_url,
        "status": safe_text(payload.get("status")) or default_status,
        "notes": safe_text(payload.get("notes")) or None,
        "date_applied": safe_text(payload.get("date_applied")) or None,
        "follow_up": safe_text(payload.get("follow_up")) or None,
        "salary_min": safe_int(payload.get("salary_min")),
        "salary_max": safe_int(payload.get("salary_max")),
        "location": safe_text(payload.get("location")) or None,
        "remote": safe_bool(payload.get("remote")),
        "source": safe_text(payload.get("source")) or "web",
    }


def tracker_row_from_job_payload(
    payload: dict[str, Any],
    *,
    safe_text: Callable[[Any], str],
    tracker_id: int | None = None,
    existing_row: dict[str, str] | None = None,
) -> dict[str, str]:
    row = {
        "date": safe_text(payload.get("date_applied")) or safe_text((existing_row or {}).get("date")),
        "company": safe_text(payload.get("company")),
        "role": safe_text(payload.get("position")),
        "score": safe_text((existing_row or {}).get("score")),
        "status": safe_text(payload.get("status")) or safe_text((existing_row or {}).get("status")) or "검토중",
        "source": safe_text(payload.get("source")) or safe_text((existing_row or {}).get("source")) or "web",
        "resume": safe_text((existing_row or {}).get("resume")),
        "report": safe_text((existing_row or {}).get("report")),
        "notes": safe_text(payload.get("notes")) or safe_text((existing_row or {}).get("notes")),
    }
    if tracker_id is not None:
        row["id"] = str(tracker_id)
    return row


def attach_resume_artifacts_to_job(
    *,
    artifacts: Any,
    connection_scope: Callable[..., Any],
    normalize_job_url: Callable[[Any], str | None],
    job_id: int | None = None,
    url: str | None = None,
    company: str | None = None,
    position: str | None = None,
) -> int | None:
    normalized_url = normalize_job_url(url)
    with connection_scope() as conn:
        row = None
        if job_id is not None:
            row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None and normalized_url:
            row = conn.execute(
                """
                SELECT id FROM jobs
                WHERE canonical_url = ? OR url = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (normalized_url, normalized_url),
            ).fetchone()
        if row is None and company and position:
            row = conn.execute(
                """
                SELECT id FROM jobs
                WHERE company = ? AND position = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (company, position),
            ).fetchone()
        if row is None:
            return None
        matched_job_id = int(row["id"])
        conn.execute(
            """
            UPDATE jobs
            SET canonical_url = COALESCE(canonical_url, ?),
                job_path = ?, report_path = ?, tailoring_path = ?, context_path = ?, html_path = ?, pdf_path = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                normalized_url,
                artifacts.job_path.as_posix(),
                artifacts.report_path.as_posix(),
                artifacts.tailoring_path.as_posix(),
                artifacts.tailored_context_path.as_posix(),
                artifacts.html_path.as_posix(),
                artifacts.pdf_path.as_posix() if artifacts.pdf_path else None,
                matched_job_id,
            ),
        )
        conn.commit()
        return matched_job_id


def save_job_record(
    payload: dict[str, Any],
    *,
    connection_scope: Callable[..., Any],
    tracker_path: Path,
    normalize_job_url: Callable[[Any], str | None],
    safe_text: Callable[[Any], str],
    safe_int: Callable[[Any], int | None],
    safe_bool: Callable[[Any], bool],
    upsert_tracker_row: Callable[[Path, dict[str, str]], dict[str, str]],
    load_tracker_row_for_job: Callable[[dict[str, Any]], dict[str, str] | None],
) -> dict[str, Any]:
    normalized = normalize_job_payload(
        payload,
        normalize_job_url=normalize_job_url,
        safe_text=safe_text,
        safe_int=safe_int,
        safe_bool=safe_bool,
    )
    with connection_scope() as conn:
        existing = None
        canonical_url = normalized["canonical_url"]
        if canonical_url:
            rows = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE canonical_url = ? OR url = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (canonical_url, canonical_url),
            ).fetchall()
            for row in rows:
                existing = row
                break

        if existing:
            merged_payload = dict(existing)
            update_values: dict[str, Any] = {}
            for field in (
                "url",
                "canonical_url",
                "location",
                "salary_min",
                "salary_max",
                "date_applied",
                "follow_up",
            ):
                if not existing.get(field) and normalized.get(field):
                    update_values[field] = normalized[field]
            if normalized["notes"] and not safe_text(existing.get("notes")):
                update_values["notes"] = normalized["notes"]
            if normalized["source"] and safe_text(existing.get("source")) in {"", "web"}:
                if safe_text(existing.get("source")) != normalized["source"]:
                    update_values["source"] = normalized["source"]
            if normalized["status"] and safe_text(existing.get("status")) in {"", "검토중"}:
                if safe_text(existing.get("status")) != normalized["status"]:
                    update_values["status"] = normalized["status"]

            merged_payload.update(update_values)
            tracker_row = upsert_tracker_row(
                tracker_path,
                tracker_row_from_job_payload(
                    normalize_job_payload(
                        merged_payload,
                        normalize_job_url=normalize_job_url,
                        safe_text=safe_text,
                        safe_int=safe_int,
                        safe_bool=safe_bool,
                        default_status=str(existing.get("status") or "검토중"),
                    ),
                    safe_text=safe_text,
                    tracker_id=safe_int(existing.get("tracker_id")),
                    existing_row=load_tracker_row_for_job(existing),
                ),
            )
            update_values["tracker_id"] = int(tracker_row["id"])
            if update_values:
                fields = [f"{field} = ?" for field in update_values]
                values = list(update_values.values())
                values.append(existing["id"])
                conn.execute(
                    f"UPDATE jobs SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
                    values,
                )
                conn.commit()
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (existing["id"],)).fetchone()
            result = dict(row or {})
            result["_save_result"] = "updated" if any(
                key != "tracker_id" for key in update_values
            ) else "existing"
            return result

        tracker_row = upsert_tracker_row(
            tracker_path,
            tracker_row_from_job_payload(normalized, safe_text=safe_text),
        )
        tracker_id = int(tracker_row["id"])
        cursor = conn.execute(
            """
            INSERT INTO jobs(
                company, position, url, canonical_url, status, notes, date_applied, follow_up,
                salary_min, salary_max, location, remote, source, tracker_id
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["company"],
                normalized["position"],
                normalized["url"],
                normalized["canonical_url"],
                normalized["status"],
                normalized["notes"],
                normalized["date_applied"],
                normalized["follow_up"],
                normalized["salary_min"],
                normalized["salary_max"],
                normalized["location"],
                normalized["remote"],
                normalized["source"],
                tracker_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    result = dict(row or {})
    result["_save_result"] = "created"
    return result


def update_job_record(
    job_id: int,
    payload: dict[str, Any],
    *,
    connection_scope: Callable[..., Any],
    tracker_path: Path,
    normalize_job_url: Callable[[Any], str | None],
    safe_text: Callable[[Any], str],
    safe_int: Callable[[Any], int | None],
    safe_bool: Callable[[Any], bool],
    upsert_tracker_row: Callable[[Path, dict[str, str]], dict[str, str]],
    job_row_api_payload: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    with connection_scope() as conn:
        existing = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")

        merged = dict(existing)
        merged.update(payload)
        normalized = normalize_job_payload(
            merged,
            normalize_job_url=normalize_job_url,
            safe_text=safe_text,
            safe_int=safe_int,
            safe_bool=safe_bool,
            default_status=str(existing.get("status") or "검토중"),
        )
        tracker_row = upsert_tracker_row(
            tracker_path,
            tracker_row_from_job_payload(
                normalized,
                safe_text=safe_text,
                tracker_id=safe_int(existing.get("tracker_id")),
            ),
        )
        tracker_id = int(tracker_row["id"])

        allowed_fields = {
            "company": normalized["company"],
            "position": normalized["position"],
            "url": normalized["url"],
            "canonical_url": normalized["canonical_url"],
            "status": normalized["status"],
            "notes": normalized["notes"],
            "date_applied": normalized["date_applied"],
            "follow_up": normalized["follow_up"],
            "salary_min": normalized["salary_min"],
            "salary_max": normalized["salary_max"],
            "location": normalized["location"],
            "remote": normalized["remote"],
            "source": normalized["source"],
        }
        fields: list[str] = []
        values: list[Any] = []
        for key in allowed_fields:
            if key not in payload:
                continue
            fields.append(f"{key} = ?")
            values.append(allowed_fields[key])
        fields.append("tracker_id = ?")
        values.append(tracker_id)

        if len(fields) == 1:
            raise HTTPException(status_code=400, detail="No fields to update")

        fields.append("updated_at = datetime('now')")
        values.append(job_id)
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return job_row_api_payload(row)


def delete_job_record(
    job_id: int,
    *,
    connection_scope: Callable[..., Any],
    tracker_path: Path,
    safe_int: Callable[[Any], int | None],
    delete_tracker_row: Callable[[Path, int], None],
) -> bool:
    with connection_scope() as conn:
        existing = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not existing:
            return False
        tracker_id = safe_int(existing.get("tracker_id"))
        if tracker_id is not None:
            delete_tracker_row(tracker_path, tracker_id)
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    return True


def bulk_update_job_records(
    job_ids: list[Any],
    payload: dict[str, Any],
    *,
    connection_scope: Callable[..., Any],
    safe_int: Callable[[Any], int | None],
    safe_text: Callable[[Any], str],
    update_job_record: Callable[[int, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    normalized_ids = sorted({safe_int(value) for value in job_ids if safe_int(value) is not None})
    if not normalized_ids:
        raise HTTPException(status_code=400, detail="No job ids selected")

    updates: dict[str, Any] = {}
    for field in ("status", "source", "follow_up"):
        raw_value = payload.get(field)
        if raw_value is None:
            continue
        normalized_value = safe_text(raw_value)
        if not normalized_value:
            continue
        updates[field] = normalized_value

    if not updates:
        raise HTTPException(status_code=400, detail="No bulk fields to update")

    placeholders = ", ".join("?" for _ in normalized_ids)
    with connection_scope() as conn:
        rows = conn.execute(
            f"SELECT id FROM jobs WHERE id IN ({placeholders})",
            normalized_ids,
        ).fetchall()
    existing_ids = sorted(int(row["id"]) for row in rows)
    missing_ids = [job_id for job_id in normalized_ids if job_id not in existing_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Missing job ids: {', '.join(str(job_id) for job_id in missing_ids)}")

    tracker_synced_fields = {"status", "source"}
    if tracker_synced_fields.intersection(updates):
        with connection_scope() as conn:
            tracker_rows = conn.execute(
                f"SELECT id, tracker_id FROM jobs WHERE id IN ({placeholders})",
                normalized_ids,
            ).fetchall()
        trackerless_ids = sorted(int(row["id"]) for row in tracker_rows if safe_int(row.get("tracker_id")) is None)
        if trackerless_ids:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Tracker-linked fields require tracker_id. "
                    f"Sync or repair these jobs first: {', '.join(str(job_id) for job_id in trackerless_ids)}"
                ),
            )

    updated_jobs = [update_job_record(job_id, updates) for job_id in normalized_ids]
    return {
        "updated_ids": normalized_ids,
        "updated_count": len(updated_jobs),
        "fields": sorted(updates.keys()),
        "field_values": updates,
        "job_labels": [f"#{job['id']} {job['company']}" for job in updated_jobs],
        "jobs": updated_jobs,
    }


def sync_tracker_rows_to_jobs(
    *,
    tracker_path: Path,
    connection_scope: Callable[..., Any],
    parse_tracker_rows: Callable[[str], list[dict[str, str]]],
) -> dict[str, int]:
    if not tracker_path.exists():
        return {"total": 0, "created": 0, "updated": 0}
    rows = parse_tracker_rows(tracker_path.read_text(encoding="utf-8"))
    created = 0
    updated = 0
    with connection_scope() as conn:
        for row in rows:
            tracker_id = int(row["id"])
            existing = conn.execute(
                """
                SELECT * FROM jobs
                WHERE tracker_id = ?
                   OR (company = ? AND position = ?)
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (tracker_id, row["company"], row["role"]),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE jobs
                    SET company = ?, position = ?, status = ?, date_applied = ?, notes = ?, source = ?, tracker_id = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        row["company"],
                        row["role"],
                        row["status"],
                        row["date"],
                        row["notes"],
                        row["source"],
                        tracker_id,
                        existing["id"],
                    ),
                )
                updated += 1
                continue
            conn.execute(
                """
                INSERT INTO jobs(
                    company, position, status, notes, date_applied, remote, source, tracker_id
                )
                VALUES(?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    row["company"],
                    row["role"],
                    row["status"],
                    row["notes"] or None,
                    row["date"] or None,
                    row["source"] or "tracker",
                    tracker_id,
                ),
            )
            created += 1
        conn.commit()
    return {"total": len(rows), "created": created, "updated": updated}
