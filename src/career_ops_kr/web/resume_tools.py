from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from career_ops_kr.utils import ensure_dir
from career_ops_kr.web.db import connection_scope


REPO_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DIR = Path(
    os.getenv(
        "CAREER_OPS_WEB_UPLOAD_DIR",
        os.getenv("CAREER_OPS_WEB_OUTPUT_DIR", (REPO_ROOT / "output").as_posix()) + "/web-uploads",
    )
)


def extract_resume_text(filename: str, content: bytes) -> str:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    if lowered.endswith(".txt") or lowered.endswith(".md"):
        return content.decode("utf-8", errors="ignore").strip()
    raise ValueError("Unsupported file type. Use PDF, TXT, or MD.")


def save_uploaded_resume(filename: str, content: bytes, *, db_path: Path | None = None) -> dict[str, Any]:
    text = extract_resume_text(filename, content)
    if not text:
        raise ValueError("Could not extract text from file.")

    ensure_dir(UPLOAD_DIR)
    safe_name = Path(filename).name
    stored_path = UPLOAD_DIR / safe_name
    suffix_index = 1
    while stored_path.exists():
        stored_path = UPLOAD_DIR / f"{stored_path.stem}-{suffix_index}{stored_path.suffix}"
        suffix_index += 1
    stored_path.write_bytes(content)

    with connection_scope(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO resumes(filename, content, file_path) VALUES(?, ?, ?)",
            (filename, text, stored_path.as_posix()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, filename, file_path, created_at FROM resumes WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return row or {}


def list_resumes(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    with connection_scope(db_path) as conn:
        rows = conn.execute(
            "SELECT id, filename, file_path, created_at FROM resumes ORDER BY created_at DESC"
        ).fetchall()
    return rows


def get_resume_content(resume_id: int | None = None, *, db_path: Path | None = None) -> dict[str, Any] | None:
    with connection_scope(db_path) as conn:
        if resume_id is None:
            return conn.execute(
                "SELECT * FROM resumes ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
