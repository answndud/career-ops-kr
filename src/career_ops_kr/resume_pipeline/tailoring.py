from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_ops_kr.resume_pipeline.models import (
    ResumeTailoringArtifacts,
    TailoredResumeContextArtifacts,
)
from career_ops_kr.utils import ensure_dir, load_yaml, parse_front_matter, slugify, title_case


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_ROLE_STOPWORDS = {
    "and",
    "backend",
    "data",
    "developer",
    "engineer",
    "engineering",
    "for",
    "platform",
    "senior",
    "software",
    "the",
    "with",
}


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        normalized = cleaned.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(cleaned)
    return unique


def _target_role_terms(value: str) -> list[str]:
    tokens = re.split(r"[^a-z0-9+#.-]+", value.lower())
    return [
        token
        for token in tokens
        if len(token) >= 3 and token not in COMMON_ROLE_STOPWORDS
    ]


def _parse_report_summary(report_text: str, report_path: Path) -> dict[str, str]:
    summary: dict[str, str] = {}
    for line in report_text.splitlines():
        if not line.startswith("- "):
            continue
        label, separator, value = line[2:].partition(":")
        if not separator:
            continue
        summary[label.strip()] = value.strip()

    required_labels = [
        "Selected Domain",
        "Selected Target Role",
        "Selected Role Profile",
        "Total Score",
        "Recommendation",
    ]
    missing = [label for label in required_labels if not summary.get(label)]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            f"Score report is missing required summary fields ({joined}): {report_path.as_posix()}"
        )
    return summary


def _extract_report_section_bullets(report_text: str, heading: str) -> list[str]:
    lines = report_text.splitlines()
    collected: list[str] = []
    in_section = False
    heading_line = f"## {heading}"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if stripped == heading_line:
                in_section = True
                continue
            if in_section:
                break
        if in_section and stripped.startswith("- "):
            collected.append(stripped[2:].strip())
    return collected


def _resolve_role_profile(
    selected_role_profile: str,
    scorecard: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    role_profiles = scorecard.get("role_profiles", {})
    normalized_target = _normalize_key(selected_role_profile)
    for key, profile in role_profiles.items():
        label = str(profile.get("label", ""))
        if _normalize_key(key) == normalized_target or _normalize_key(label) == normalized_target:
            return str(key), profile
    return None, {}


def _collect_profile_keywords(
    profile_key: str | None,
    role_profile: dict[str, Any],
    selected_target_role: str,
) -> list[str]:
    keywords = _unique_strings(
        [
            *(str(keyword) for keyword in role_profile.get("stack_keywords", [])),
            *(str(keyword) for keyword in role_profile.get("match_keywords", [])),
            *(str(keyword) for keyword in role_profile.get("specialization_keywords", [])),
            *(_target_role_terms(selected_target_role)),
        ]
    )

    if profile_key == "backend":
        keywords = [keyword for keyword in keywords if keyword.lower() not in {"backend"}]
    return keywords


def _matched_job_keywords(job_text: str, keywords: list[str], *, limit: int = 8) -> list[str]:
    matched = [keyword for keyword in keywords if keyword.lower() in job_text]
    return matched[:limit]


def _base_context_skills(base_context: dict[str, Any]) -> list[str]:
    return [str(skill) for skill in base_context.get("skills", [])]


def _matching_priority(value: str, keywords: list[str]) -> tuple[int, int]:
    lower = value.lower()
    matched = [keyword for keyword in keywords if keyword.lower() in lower]
    if not matched:
        return (0, 0)
    longest = max(len(keyword) for keyword in matched)
    return (len(matched), longest)


def _reorder_skills(existing_skills: list[str], emphasis_keywords: list[str]) -> list[str]:
    original = [str(skill) for skill in existing_skills]
    emphasized: list[str] = []
    remaining: list[str] = []
    for skill in original:
        if skill.lower() in {keyword.lower() for keyword in emphasis_keywords}:
            emphasized.append(skill)
        else:
            remaining.append(skill)
    return emphasized + remaining


def _entry_text(entry: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("role", "company", "period", "location", "name", "subtitle", "program", "school"):
        if key in entry and entry[key]:
            values.append(str(entry[key]))
    bullets = entry.get("bullets", [])
    if isinstance(bullets, list):
        values.extend(str(item) for item in bullets)
    return "\n".join(values)


def _sort_resume_entries(entries: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    indexed_entries = list(enumerate(entries))
    ranked = sorted(
        indexed_entries,
        key=lambda item: (
            _matching_priority(_entry_text(item[1]), keywords)[0],
            _matching_priority(_entry_text(item[1]), keywords)[1],
            -item[0],
        ),
        reverse=True,
    )
    return [entry for _, entry in ranked]


def _build_tailoring_summary(
    job_title: str,
    selected_role_profile: str,
    recommendation: str,
    matched_keywords: list[str],
) -> str:
    focus = ", ".join(matched_keywords[:3]) if matched_keywords else selected_role_profile
    return (
        f"Resume version for {job_title} with emphasis on {focus}. "
        f"Current score recommendation: {recommendation}."
    )


def create_resume_tailoring_packet(
    job_path: Path,
    report_path: Path,
    *,
    out: Path | None = None,
    base_context_path: Path | None = None,
    scorecard_path: Path = REPO_ROOT / "config" / "scorecard.kr.yml",
    overwrite: bool = False,
) -> ResumeTailoringArtifacts:
    if not job_path.exists():
        raise ValueError(f"Job markdown path does not exist: {job_path.as_posix()}")
    if not report_path.exists():
        raise ValueError(f"Score report path does not exist: {report_path.as_posix()}")
    if base_context_path and not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")
    if not scorecard_path.exists():
        raise ValueError(f"Scorecard path does not exist: {scorecard_path.as_posix()}")

    metadata, job_body = parse_front_matter(job_path)
    report_text = report_path.read_text(encoding="utf-8")
    summary = _parse_report_summary(report_text, report_path)
    scorecard = load_yaml(scorecard_path)

    job_title = title_case(str(metadata.get("title") or job_path.stem))
    company = title_case(str(metadata.get("company") or "Unknown"))
    if company == "Unknown":
        report_title = report_text.splitlines()[0].removeprefix("# ").strip() if report_text.strip() else ""
        if " - " in report_title:
            company = title_case(report_title.split(" - ", 1)[0])

    selected_domain = summary["Selected Domain"]
    selected_target_role = summary["Selected Target Role"]
    selected_role_profile = summary["Selected Role Profile"]
    recommendation = summary["Recommendation"]
    total_score_raw = summary["Total Score"].removesuffix("/5").strip()
    total_score = float(total_score_raw)
    language_signal = [
        value.strip()
        for value in summary.get("Language Signal", "ko").split(",")
        if value.strip()
    ]

    role_profile_key, role_profile = _resolve_role_profile(selected_role_profile, scorecard)
    profile_keywords = _collect_profile_keywords(role_profile_key, role_profile, selected_target_role)
    job_text = f"{job_title}\n{job_body}".lower()
    skills_to_emphasize = _matched_job_keywords(job_text, profile_keywords)

    base_context: dict[str, Any] = {}
    if base_context_path:
        base_context = json.loads(base_context_path.read_text(encoding="utf-8"))
    base_skills = _base_context_skills(base_context)
    base_context_text = json.dumps(base_context, ensure_ascii=False).lower() if base_context else ""
    matched_resume_skills = [
        skill for skill in base_skills if skill.lower() in job_text
    ]
    missing_focus_keywords = [
        keyword for keyword in skills_to_emphasize if keyword.lower() not in base_context_text
    ]

    why_it_fits = _extract_report_section_bullets(report_text, "Why It Fits")
    risks = _extract_report_section_bullets(report_text, "Risks")

    date = summary.get("Date") or datetime.now(UTC).date().isoformat()
    default_output = (
        Path("output")
        / "resume-tailoring"
        / f"{date}-{slugify(f'{company}-{job_title}', fallback='resume-tailoring')}.json"
    )
    output_path = out or default_output
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Resume tailoring packet already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )

    packet: dict[str, Any] = {
        "source": {
            "job_path": job_path.as_posix(),
            "report_path": report_path.as_posix(),
            "base_context_path": base_context_path.as_posix() if base_context_path else None,
            "scorecard_path": scorecard_path.as_posix(),
        },
        "job": {
            "company": company,
            "title": job_title,
            "url": metadata.get("url"),
            "source": metadata.get("source", "manual"),
        },
        "selection": {
            "selected_domain": selected_domain,
            "selected_target_role": selected_target_role,
            "selected_role_profile": selected_role_profile,
            "total_score": total_score,
            "recommendation": recommendation,
            "seniority_signal": summary.get("Seniority Signal", "mid"),
            "work_mode_signal": summary.get("Work Mode Signal", "unknown"),
            "language_signal": language_signal,
        },
        "tailoring": {
            "headline": selected_target_role if selected_target_role != "General" else job_title,
            "summary": _build_tailoring_summary(
                job_title,
                selected_role_profile,
                recommendation,
                skills_to_emphasize,
            ),
            "skills_to_emphasize": skills_to_emphasize,
            "matched_resume_skills": matched_resume_skills,
            "missing_focus_keywords": missing_focus_keywords,
            "experience_focus": [
                (
                    f"Move bullets proving {', '.join(skills_to_emphasize[:3])} closer to the top."
                    if skills_to_emphasize
                    else f"Move the most relevant {selected_role_profile} experience closer to the top."
                ),
                f"Make recent experience read like a direct match for {selected_target_role}.",
            ],
            "project_focus": [
                (
                    f"Highlight projects that show {', '.join(skills_to_emphasize[:2])} in production."
                    if len(skills_to_emphasize) >= 2
                    else f"Highlight one project that supports the {selected_target_role} narrative."
                ),
                f"Prefer {selected_domain} work that reduces perceived onboarding risk.",
            ],
            "keywords": skills_to_emphasize,
            "notes": [
                f"Recommendation from score report: {recommendation}",
                *[f"Fit signal: {line}" for line in why_it_fits[:2]],
                *[f"Risk check: {line}" for line in risks[:2]],
            ],
        },
    }

    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ResumeTailoringArtifacts(output_path=output_path, packet=packet)


def apply_resume_tailoring_packet(
    tailoring_path: Path,
    base_context_path: Path,
    *,
    out: Path | None = None,
    overwrite: bool = False,
) -> TailoredResumeContextArtifacts:
    if not tailoring_path.exists():
        raise ValueError(f"Resume tailoring packet does not exist: {tailoring_path.as_posix()}")
    if not base_context_path.exists():
        raise ValueError(f"Base resume context does not exist: {base_context_path.as_posix()}")

    packet = json.loads(tailoring_path.read_text(encoding="utf-8"))
    base_context = json.loads(base_context_path.read_text(encoding="utf-8"))

    tailoring = packet.get("tailoring")
    selection = packet.get("selection")
    job = packet.get("job")
    if not isinstance(tailoring, dict) or not isinstance(selection, dict) or not isinstance(job, dict):
        raise ValueError(f"Invalid resume tailoring packet schema: {tailoring_path.as_posix()}")

    for required_key in ("headline", "summary", "skills_to_emphasize", "experience_focus", "project_focus", "notes"):
        if required_key not in tailoring:
            raise ValueError(
                f"Resume tailoring packet is missing '{required_key}': {tailoring_path.as_posix()}"
            )

    company = title_case(str(job.get("company") or "Unknown"))
    title = title_case(str(job.get("title") or "Resume"))
    date = datetime.now(UTC).date().isoformat()
    default_output = (
        Path("output")
        / "resume-contexts"
        / f"{date}-{slugify(f'{company}-{title}', fallback='resume-context')}.json"
    )
    output_path = out or default_output
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Tailored resume context already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )

    tailored_context = copy.deepcopy(base_context)
    tailored_context["headline"] = str(tailoring["headline"])
    tailored_context["summary"] = str(tailoring["summary"])

    existing_skills = [str(skill) for skill in tailored_context.get("skills", [])]
    emphasis_keywords = [str(keyword) for keyword in tailoring.get("skills_to_emphasize", [])]
    ranking_keywords = _unique_strings(
        [
            *emphasis_keywords,
            *(str(keyword) for keyword in tailoring.get("keywords", [])),
            *(str(skill) for skill in tailoring.get("matched_resume_skills", [])),
            *(_target_role_terms(str(selection.get("selected_target_role", "")))),
        ]
    )

    if existing_skills:
        tailored_context["skills"] = _reorder_skills(existing_skills, emphasis_keywords)

    experience = tailored_context.get("experience")
    if isinstance(experience, list):
        tailored_context["experience"] = _sort_resume_entries(experience, ranking_keywords)

    projects = tailored_context.get("projects")
    if isinstance(projects, list):
        tailored_context["projects"] = _sort_resume_entries(projects, ranking_keywords)

    tailored_context["tailoringGuidance"] = {
        "tailoring_path": tailoring_path.as_posix(),
        "job": {
            "company": company,
            "title": title,
            "url": job.get("url"),
            "source": job.get("source"),
        },
        "selection": {
            "selected_domain": selection.get("selected_domain"),
            "selected_target_role": selection.get("selected_target_role"),
            "selected_role_profile": selection.get("selected_role_profile"),
            "total_score": selection.get("total_score"),
            "recommendation": selection.get("recommendation"),
        },
        "focus": {
            "skills_to_emphasize": emphasis_keywords,
            "missing_focus_keywords": [str(item) for item in tailoring.get("missing_focus_keywords", [])],
            "experience_focus": [str(item) for item in tailoring.get("experience_focus", [])],
            "project_focus": [str(item) for item in tailoring.get("project_focus", [])],
            "notes": [str(item) for item in tailoring.get("notes", [])],
        },
    }

    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(tailored_context, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return TailoredResumeContextArtifacts(output_path=output_path, context=tailored_context)


__all__ = [
    "apply_resume_tailoring_packet",
    "create_resume_tailoring_packet",
]
