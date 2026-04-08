from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from career_ops_kr.portals import canonicalize_job_url
from career_ops_kr.utils import ensure_dir


PIPELINE_TEMPLATE = "# Pipeline Inbox\n\n## Pending\n\n## Processed\n"
LOCK_STALE_SECONDS = 3600


class PipelineLockError(RuntimeError):
    pass


def pipeline_lock_path(path: str | Path) -> Path:
    target = Path(path).resolve()
    return target.with_name(f"{target.name}.lock")


def _read_lock_metadata(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _pid_is_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_age_seconds(path: str | Path) -> float | None:
    target = Path(path)
    try:
        return max(0.0, datetime.now(UTC).timestamp() - target.stat().st_mtime)
    except OSError:
        return None


def _is_stale_lock(path: str | Path) -> bool:
    metadata = _read_lock_metadata(path)
    pid = metadata.get("pid")
    if isinstance(pid, int):
        return not _pid_is_running(pid)

    age_seconds = _lock_age_seconds(path)
    return age_seconds is not None and age_seconds >= LOCK_STALE_SECONDS


@contextmanager
def acquire_pipeline_lock(path: str | Path) -> Iterator[Path]:
    target = ensure_pipeline_file(path).resolve()
    lock_path = pipeline_lock_path(target)
    ensure_dir(lock_path.parent)

    token = uuid4().hex
    metadata = {
        "token": token,
        "pid": os.getpid(),
        "created_at": datetime.now(UTC).isoformat(),
        "pipeline": target.as_posix(),
    }

    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _is_stale_lock(lock_path):
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise PipelineLockError(
                        f"Failed to clear stale pipeline lock {lock_path.as_posix()}: {exc}"
                    ) from exc
                continue

            current = _read_lock_metadata(lock_path)
            holder = current.get("pid", "unknown")
            created_at = current.get("created_at", "unknown")
            raise PipelineLockError(
                f"Pipeline is already being processed by pid {holder} since {created_at}: "
                f"{lock_path.as_posix()}"
            )
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            break

    try:
        yield lock_path
    finally:
        current = _read_lock_metadata(lock_path)
        if current.get("token") == token:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def ensure_pipeline_file(path: str | Path) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    if not target.exists():
        target.write_text(PIPELINE_TEMPLATE, encoding="utf-8")
    return target


def list_pending_urls(path: str | Path) -> list[str]:
    target = ensure_pipeline_file(path)
    seen: set[str] = set()
    urls: list[str] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- [ ] "):
            continue
        url = canonicalize_job_url(line[6:].strip())
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def mark_urls_processed(path: str | Path, urls: list[str]) -> int:
    if not urls:
        return 0

    target = ensure_pipeline_file(path)
    processed_urls = {canonicalize_job_url(url) for url in urls}
    lines = target.read_text(encoding="utf-8").splitlines()
    changed = 0
    updated_lines: list[str] = []

    for line in lines:
        if line.startswith("- [ ] "):
            url = canonicalize_job_url(line[6:].strip())
            if url in processed_urls:
                updated_lines.append(f"- [x] {url}")
                changed += 1
                continue
        updated_lines.append(line)

    target.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    return changed
