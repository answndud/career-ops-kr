from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WebPaths:
    repo_root: Path
    output_dir: Path
    tracker_path: Path
    jd_dir: Path
    report_dir: Path
    web_resume_output_dir: Path
    live_smoke_report_dir: Path
    web_db_output_dir: Path
