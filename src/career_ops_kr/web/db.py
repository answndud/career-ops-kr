from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from career_ops_kr.utils import ensure_dir
from career_ops_kr.portals import canonicalize_job_url


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "career-ops-web.db"
LEGACY_REMOVED_SETTING_KEYS = {
    "ADZUNA_APP_ID",
    "ADZUNA_API_KEY",
}


def resolve_db_path(db_path: Path | None = None) -> Path:
    if db_path is not None:
        return db_path
    env_value = os.getenv("CAREER_OPS_WEB_DB")
    return Path(env_value) if env_value else DEFAULT_DB_PATH


def _dict_factory(cursor: sqlite3.Cursor, row: tuple[object, ...]) -> dict[str, object]:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            position TEXT NOT NULL,
            url TEXT,
            status TEXT NOT NULL DEFAULT 'saved',
            notes TEXT,
            date_applied TEXT,
            follow_up TEXT,
            salary_min INTEGER,
            salary_max INTEGER,
            location TEXT,
            remote INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            file_path TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resume_id INTEGER NOT NULL REFERENCES resumes(id),
            job_id INTEGER REFERENCES jobs(id),
            job_description TEXT NOT NULL,
            match_score REAL,
            analysis_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ai_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            job_id INTEGER REFERENCES jobs(id),
            input_json TEXT NOT NULL,
            output TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at);
        CREATE INDEX IF NOT EXISTS idx_resumes_created_at ON resumes(created_at);
        """
    )
    _ensure_column(conn, "jobs", "source", "TEXT")
    _ensure_column(conn, "jobs", "canonical_url", "TEXT")
    _ensure_column(conn, "jobs", "tracker_id", "INTEGER")
    _ensure_column(conn, "jobs", "job_path", "TEXT")
    _ensure_column(conn, "jobs", "report_path", "TEXT")
    _ensure_column(conn, "jobs", "tailoring_path", "TEXT")
    _ensure_column(conn, "jobs", "context_path", "TEXT")
    _ensure_column(conn, "jobs", "html_path", "TEXT")
    _ensure_column(conn, "jobs", "pdf_path", "TEXT")
    _delete_legacy_settings(conn)
    _backfill_jobs_canonical_urls(conn)
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    column_names = {str(row["name"]) for row in rows}
    if column in column_names:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _delete_legacy_settings(conn: sqlite3.Connection) -> None:
    if not LEGACY_REMOVED_SETTING_KEYS:
        return
    placeholders = ", ".join("?" for _ in LEGACY_REMOVED_SETTING_KEYS)
    conn.execute(
        f"DELETE FROM settings WHERE key IN ({placeholders})",
        tuple(sorted(LEGACY_REMOVED_SETTING_KEYS)),
    )


def _backfill_jobs_canonical_urls(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id, url, canonical_url FROM jobs").fetchall()
    for row in rows:
        url = str(row.get("url") or "").strip()
        canonical_url = str(row.get("canonical_url") or "").strip()
        if not url:
            continue
        normalized = canonicalize_job_url(url)
        if canonical_url == normalized:
            continue
        conn.execute(
            "UPDATE jobs SET canonical_url = ? WHERE id = ?",
            (normalized, row["id"]),
        )


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    target = resolve_db_path(db_path)
    ensure_dir(target.parent)
    conn = sqlite3.connect(target)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    init_schema(conn)
    return conn


@contextmanager
def connection_scope(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def create_database_backup(*, backup_dir: Path | None = None, db_path: Path | None = None) -> Path:
    source_path = resolve_db_path(db_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target_dir = backup_dir or (source_path.parent / "backups")
    ensure_dir(target_dir)
    backup_path = target_dir / f"{source_path.stem}-{timestamp}.sqlite3"

    source_conn = get_connection(source_path)
    try:
        target_conn = sqlite3.connect(backup_path)
        try:
            source_conn.backup(target_conn)
        finally:
            target_conn.close()
    finally:
        source_conn.close()
    return backup_path


def export_database_snapshot(*, out_path: Path, db_path: Path | None = None) -> Path:
    payload: dict[str, object]
    with connection_scope(db_path) as conn:
        payload = {
            "version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "tables": {
                "settings": _filtered_settings_rows(conn.execute("SELECT * FROM settings ORDER BY key").fetchall()),
                "jobs": conn.execute("SELECT * FROM jobs ORDER BY id").fetchall(),
                "resumes": conn.execute("SELECT * FROM resumes ORDER BY id").fetchall(),
                "match_results": conn.execute("SELECT * FROM match_results ORDER BY id").fetchall(),
                "ai_outputs": conn.execute("SELECT * FROM ai_outputs ORDER BY id").fetchall(),
            },
        }
    ensure_dir(out_path.parent)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def import_database_snapshot(
    snapshot_path: Path,
    *,
    db_path: Path | None = None,
    backup_dir: Path | None = None,
) -> dict[str, object]:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("tables"), dict):
        raise ValueError("Invalid database snapshot format.")

    tables_payload = payload["tables"]
    required_tables = ["settings", "jobs", "resumes", "match_results", "ai_outputs"]
    for table in required_tables:
        if table not in tables_payload or not isinstance(tables_payload[table], list):
            raise ValueError(f"Database snapshot is missing table: {table}")

    tables_payload["settings"] = _filtered_settings_rows(tables_payload["settings"])

    backup_path = create_database_backup(backup_dir=backup_dir, db_path=db_path)

    with connection_scope(db_path) as conn:
        conn.execute("DELETE FROM match_results")
        conn.execute("DELETE FROM ai_outputs")
        conn.execute("DELETE FROM resumes")
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM settings")

        for table in required_tables:
            _bulk_insert_rows(conn, table, tables_payload[table])

        for table in ["jobs", "resumes", "match_results", "ai_outputs"]:
            _reset_sqlite_sequence(conn, table)
        conn.commit()

    return {
        "backup_path": backup_path.as_posix(),
        "counts": {table: len(tables_payload[table]) for table in required_tables},
    }


def _filtered_settings_rows(rows: list[object]) -> list[object]:
    filtered: list[object] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            filtered.append(raw_row)
            continue
        key = str(raw_row.get("key") or "")
        if key in LEGACY_REMOVED_SETTING_KEYS:
            continue
        filtered.append(raw_row)
    return filtered


def _bulk_insert_rows(conn: sqlite3.Connection, table: str, rows: list[object]) -> None:
    if not rows:
        return

    table_columns = [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            raise ValueError(f"Invalid row format for table: {table}")
        columns = [column for column in table_columns if column in raw_row]
        if not columns:
            continue
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(columns)
        values = [raw_row[column] for column in columns]
        conn.execute(
            f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",
            values,
        )


def _reset_sqlite_sequence(conn: sqlite3.Connection, table: str) -> None:
    try:
        max_row = conn.execute(f"SELECT MAX(id) AS max_id FROM {table}").fetchone()
        max_id = int(max_row["max_id"] or 0)
        conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
        if max_id:
            conn.execute("INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)", (table, max_id))
    except sqlite3.OperationalError:
        return
