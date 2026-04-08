from __future__ import annotations

from pathlib import Path
from typing import Any

from career_ops_kr.utils import ensure_dir, load_yaml


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


def _iter_addition_paths(additions_dir: Path, *, recursive: bool) -> list[Path]:
    if not additions_dir.exists():
        return []
    if recursive:
        return sorted(path for path in additions_dir.rglob("*.tsv") if path.is_file())
    return sorted(path for path in additions_dir.glob("*.tsv") if path.is_file())
