from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from career_ops_kr.tracker import merge_tracker_additions, normalize_tracker_statuses, parse_tracker_rows


@dataclass(slots=True)
class VerifyResult:
    missing: list[str]
    duplicates: list[str]
    missing_reports: list[str]

    @property
    def ok(self) -> bool:
        return not (self.missing or self.duplicates or self.missing_reports)


def run_merge_tracker(
    tracker_path: Path,
    additions_dir: Path,
    *,
    recursive: bool,
) -> int:
    return merge_tracker_additions(
        tracker_path,
        additions_dir,
        recursive=recursive,
    )


def run_normalize_statuses(tracker_path: Path) -> int:
    return normalize_tracker_statuses(tracker_path)


def run_verify() -> VerifyResult:
    required = [
        Path("config/profile.example.yml"),
        Path("config/profile.yml"),
        Path("config/states.yml"),
        Path("config/scorecard.kr.yml"),
        Path("data/applications.md"),
        Path("data/pipeline.md"),
    ]
    missing = [path.as_posix() for path in required if not path.exists()]
    rows = parse_tracker_rows(Path("data/applications.md").read_text(encoding="utf-8"))

    seen: set[tuple[str, str]] = set()
    duplicates: list[str] = []
    missing_reports: list[str] = []
    for row in rows:
        key = (row["company"].lower(), row["role"].lower())
        if key in seen:
            duplicates.append(f"{row['company']}::{row['role']}")
        seen.add(key)
        if row["report"] and row["report"] != "" and not Path(row["report"]).exists():
            missing_reports.append(row["report"])

    return VerifyResult(
        missing=missing,
        duplicates=duplicates,
        missing_reports=missing_reports,
    )
