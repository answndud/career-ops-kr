from __future__ import annotations

from pathlib import Path
from typing import Any

from career_ops_kr.utils import load_yaml
from career_ops_kr.web.artifacts import generated_resume_snapshot
from career_ops_kr.web.db import connection_scope
from career_ops_kr.web.followups import build_follow_up_agenda
from career_ops_kr.web.jobs_view import attach_generated_resume_job_signals, job_row_with_ui_state
from career_ops_kr.web.paths import WebPaths


def get_dashboard_snapshot(*, paths: WebPaths) -> dict[str, Any]:
    with connection_scope() as conn:
        total_jobs = conn.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]
        total_resumes = conn.execute("SELECT COUNT(*) AS count FROM resumes").fetchone()["count"]
        status_counts = conn.execute(
            "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status ORDER BY status"
        ).fetchall()
        recent_job_rows = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT 5").fetchall()
        follow_up_rows = conn.execute(
            """
            SELECT id, company, position, status, source, follow_up, notes, updated_at
            FROM jobs
            WHERE follow_up IS NOT NULL OR status IN ('검토중', '지원예정')
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        recent_resumes = conn.execute(
            "SELECT id, filename, created_at FROM resumes ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
    generated_outputs = generated_resume_snapshot(paths=paths, limit=6)
    follow_up_agenda = build_follow_up_agenda(list(follow_up_rows))
    recent_jobs = [job_row_with_ui_state(row, paths=paths) for row in recent_job_rows]
    recent_generated_resumes = attach_generated_resume_job_signals(generated_outputs["items"], paths=paths)
    return {
        "totalJobs": total_jobs,
        "totalResumes": total_resumes,
        "statusCounts": status_counts,
        "recentJobs": recent_jobs,
        "upcomingFollowUps": follow_up_agenda["preview_items"],
        "followUpAgenda": follow_up_agenda,
        "recentResumes": recent_resumes,
        "generatedResumeCount": generated_outputs["total"],
        "generatedWebResumeCount": generated_outputs["web_total"],
        "generatedCliResumeCount": generated_outputs["cli_total"],
        "recentGeneratedResumes": recent_generated_resumes,
    }


def get_follow_up_agenda(*, horizon_days: int = 7) -> dict[str, Any]:
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT id, company, position, status, source, follow_up, notes, updated_at
            FROM jobs
            WHERE follow_up IS NOT NULL OR status IN ('검토중', '지원예정')
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return build_follow_up_agenda(list(rows), horizon_days=horizon_days)


def default_web_profile_path(*, default_profile_path: Path, repo_root: Path) -> Path:
    if default_profile_path.exists():
        return default_profile_path
    return repo_root / "config" / "profile.example.yml"


def tracker_status_choices(*, repo_root: Path) -> list[str]:
    states = load_yaml(repo_root / "config" / "states.yml")
    canonical = states.get("canonical", [])
    return [str(value) for value in canonical if str(value).strip()]


def resume_preset_options(
    *,
    resume_presets: dict[tuple[str, str], Path],
    template_presets: dict[str, Path],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    role_labels = {
        "backend": "Backend",
        "platform": "Platform",
        "data-platform": "Data-Platform",
        "data-ai": "Data-AI",
    }
    language_labels = {"ko": "한국어", "en": "English"}
    for (role_key, language), context_path in resume_presets.items():
        template_path = template_presets[language]
        options.append(
            {
                "key": f"{role_key}:{language}",
                "role_key": role_key,
                "role_label": role_labels.get(role_key, role_key),
                "language": language,
                "language_label": language_labels.get(language, language),
                "context_path": context_path.as_posix(),
                "template_path": template_path.as_posix(),
            }
        )
    return options


def resolve_resume_preset(
    role_key: str,
    language: str,
    *,
    resume_presets: dict[tuple[str, str], Path],
    template_presets: dict[str, Path],
) -> tuple[Path, Path]:
    normalized_role = role_key.strip().lower()
    normalized_language = language.strip().lower()
    context_path = resume_presets.get((normalized_role, normalized_language))
    if context_path is None:
        raise ValueError(f"Unsupported resume preset: role={role_key}, language={language}")
    return context_path, template_presets[normalized_language]
