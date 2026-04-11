from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from career_ops_kr.portals import canonicalize_job_url


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def safe_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_bool(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "on"} else 0


def coerce_path(value: Any, *, repo_root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def safe_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def path_exists(value: Any, *, repo_root: Path) -> bool:
    path = coerce_path(value, repo_root=repo_root)
    return bool(path and path.exists())


def parse_tracker_date(value: str | None) -> date | None:
    raw_value = safe_text(value)
    if not raw_value:
        return None
    try:
        return date.fromisoformat(raw_value[:10])
    except ValueError:
        return None


def normalize_job_url(url: str | None) -> str | None:
    normalized = safe_text(url)
    if not normalized:
        return None
    return canonicalize_job_url(normalized)
