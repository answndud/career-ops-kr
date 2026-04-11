from __future__ import annotations

from pathlib import Path

from career_ops_kr.web.paths import WebPaths


def resolve_output_subdir(*, configured_path: Path | None, output_dir: Path, dirname: str) -> Path:
    if configured_path is not None:
        return configured_path
    return output_dir / dirname


def build_web_paths(
    *,
    repo_root: Path,
    output_dir: Path,
    tracker_path: Path,
    jd_dir: Path,
    report_dir: Path,
    web_resume_output_dir: Path | None = None,
    live_smoke_report_dir: Path | None = None,
) -> WebPaths:
    return WebPaths(
        repo_root=repo_root,
        output_dir=output_dir,
        tracker_path=tracker_path,
        jd_dir=jd_dir,
        report_dir=report_dir,
        web_resume_output_dir=resolve_output_subdir(
            configured_path=web_resume_output_dir,
            output_dir=output_dir,
            dirname="web-resumes",
        ),
        live_smoke_report_dir=resolve_output_subdir(
            configured_path=live_smoke_report_dir,
            output_dir=output_dir,
            dirname="live-smoke",
        ),
        web_db_output_dir=output_dir / "web-db",
    )


__all__ = ["build_web_paths", "resolve_output_subdir"]
