from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from career_ops_kr.utils import ensure_dir, load_yaml, parse_front_matter, slugify, title_case


@dataclass(slots=True)
class ScoreJobArtifacts:
    report_path: Path
    tracker_path: Path | None
    total_score: float
    recommendation: str


@dataclass(frozen=True, slots=True)
class DomainCandidateScore:
    domain_key: str
    label: str
    anchor_score: int
    signal_score: int
    total_score: int
    total_ratio: float
    tie_break_score: int


@dataclass(frozen=True, slots=True)
class RoleCandidateScore:
    role_name: str
    profile_key: str
    preferred_match: bool
    anchor_score: int
    signal_score: int
    total_score: int
    keyword_total: int
    match_ratio: float
    target_order: int


class ScoreJobError(ValueError):
    pass


def _unique_keywords(*groups: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for keyword in group:
            normalized = keyword.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
    return unique


def _count_matches(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def _score_by_ratio(matches: int, total: int) -> float:
    if total == 0:
        return 2.0
    ratio = matches / total
    if ratio >= 0.7:
        return 5.0
    if ratio >= 0.4:
        return 4.0
    if ratio >= 0.2:
        return 3.0
    if ratio >= 0.08:
        return 2.0
    return 1.0


def _detect_work_mode(text: str, rules: dict[str, list[str]]) -> str:
    for label, keywords in rules.items():
        if any(keyword.lower() in text for keyword in keywords):
            return label
    return "unknown"


def _detect_language_need(text: str, rules: dict[str, list[str]]) -> list[str]:
    matched = [label for label, keywords in rules.items() if any(keyword.lower() in text for keyword in keywords)]
    return matched or ["ko"]


def _detect_seniority(text: str, rules: dict[str, list[str]]) -> str:
    matches: list[tuple[int, int, str]] = []
    priority = {"junior": 0, "mid": 1, "senior": 2}
    for label, keywords in rules.items():
        count = _count_matches(text, [keyword.lower() for keyword in keywords])
        if count <= 0:
            continue
        matches.append((count, priority.get(label, 0), label))

    if not matches:
        return "mid"

    return max(matches, key=lambda item: (item[0], item[1]))[2]


def _detect_compensation_signal(text: str) -> float:
    negative_phrases = [
        "no compensation",
        "compensation not disclosed",
        "compensation undisclosed",
        "salary not disclosed",
        "salary undisclosed",
        "no salary",
        "without salary",
        "연봉 미기재",
        "연봉 비공개",
    ]
    if any(phrase in text for phrase in negative_phrases):
        return 2.0

    compensation_keywords = ["salary", "compensation", "연봉", "stock", "equity", "bonus", "스톡옵션"]
    return 4.0 if any(keyword in text for keyword in compensation_keywords) else 2.0


def _detect_unsupported_role_family(title_text: str, rules: dict[str, list[str]]) -> str | None:
    matches: list[tuple[int, str]] = []
    label_overrides = {
        "product_design": "Product Design",
        "qa": "QA",
        "embedded": "Embedded",
        "game_client": "Game Client",
    }
    for label, keywords in rules.items():
        count = _count_matches(title_text, [keyword.lower() for keyword in keywords])
        if count <= 0:
            continue
        matches.append((count, label))
    if not matches:
        return None
    selected_label = max(matches, key=lambda item: item[0])[1]
    return label_overrides.get(selected_label, selected_label.replace("_", " ").strip())


def _weighted_average(scores: dict[str, float], weights: dict[str, int]) -> float:
    total_weight = sum(weights.values())
    weighted = sum(scores[key] * weight for key, weight in weights.items())
    return round(weighted / total_weight, 1)


def _company_from_metadata(metadata: dict[str, Any]) -> str:
    if metadata.get("company"):
        return title_case(str(metadata["company"]))
    if metadata.get("url"):
        return title_case(httpx.URL(str(metadata["url"])).host or "Unknown")
    return "Unknown"


def _role_terms(target_role: dict[str, Any]) -> list[str]:
    terms = [str(target_role.get("name", ""))]
    terms.extend(str(keyword) for keyword in target_role.get("keywords", []))
    return _unique_keywords(terms)


def _infer_role_profile_key(target_role: dict[str, Any], role_profiles: dict[str, Any]) -> str | None:
    if not role_profiles:
        return None

    explicit_profile = target_role.get("scorecard_profile")
    if explicit_profile:
        profile_key = str(explicit_profile)
        if profile_key not in role_profiles:
            raise ScoreJobError(f"Unknown scorecard profile '{profile_key}' in target_roles.")
        return profile_key

    target_text = " ".join(_role_terms(target_role))
    scores: dict[str, int] = {}
    for key, profile in role_profiles.items():
        profile_keywords = _unique_keywords(
            [str(profile.get("label", ""))],
            [str(keyword) for keyword in profile.get("match_keywords", [])],
        )
        scores[key] = _count_matches(target_text, profile_keywords)

    return max(scores, key=scores.get) if scores else None


def _score_role_domains(
    job_text: str,
    target_roles: list[dict[str, Any]],
    role_profiles: dict[str, Any],
    domains: dict[str, Any],
) -> list[DomainCandidateScore]:
    if not target_roles or not role_profiles or not domains:
        return []

    available_domains: list[str] = []
    for target_role in target_roles:
        role_key = _infer_role_profile_key(target_role, role_profiles)
        if role_key is None:
            continue
        role_profile = role_profiles.get(role_key, {})
        domain_key = str(role_profile.get("domain", "")).strip()
        if not domain_key or domain_key in available_domains:
            continue
        available_domains.append(domain_key)

    if not available_domains:
        return []

    candidates: list[DomainCandidateScore] = []
    for domain_key in available_domains:
        domain = domains.get(domain_key, {})
        anchor_keywords = [str(keyword) for keyword in domain.get("anchor_keywords", [])]
        signal_keywords = [str(keyword) for keyword in domain.get("signal_keywords", [])]
        domain_keywords = _unique_keywords(anchor_keywords, signal_keywords)
        anchor_score = _count_matches(job_text, anchor_keywords)
        signal_score = _count_matches(job_text, signal_keywords)
        total_score = _count_matches(job_text, domain_keywords)
        total_ratio = total_score / len(domain_keywords) if domain_keywords else 0.0
        tie_break_keywords = [str(keyword) for keyword in domain.get("tie_break_anchor_keywords", [])]
        candidates.append(
            DomainCandidateScore(
                domain_key=domain_key,
                label=str(domain.get("label") or domain_key.title()),
                anchor_score=anchor_score,
                signal_score=signal_score,
                total_score=total_score,
                total_ratio=total_ratio,
                tie_break_score=_count_matches(job_text, tie_break_keywords),
            )
        )

    return candidates


def _select_role_domain(
    job_text: str,
    target_roles: list[dict[str, Any]],
    role_profiles: dict[str, Any],
    domains: dict[str, Any],
) -> tuple[str | None, list[DomainCandidateScore]]:
    candidates = _score_role_domains(job_text, target_roles, role_profiles, domains)

    if not candidates:
        return None, []

    ranked_candidates = sorted(
        candidates,
        key=lambda item: (item.total_score, item.anchor_score, item.signal_score, item.total_ratio),
        reverse=True,
    )
    selected_candidate = ranked_candidates[0]
    if len(ranked_candidates) >= 2:
        second_candidate = ranked_candidates[1]
        if {
            selected_candidate.domain_key,
            second_candidate.domain_key,
        } == {"platform", "data"} and abs(selected_candidate.total_score - second_candidate.total_score) <= 1:
            # Do not overturn the total-signal winner on a one-keyword tie-break wobble.
            if second_candidate.tie_break_score >= selected_candidate.tie_break_score + 2:
                selected_candidate = second_candidate
    if selected_candidate.total_score <= 0 or selected_candidate.total_ratio < 0.12:
        return None, ranked_candidates
    return selected_candidate.domain_key, ranked_candidates


def _select_data_specialization(job_text: str, role_profiles: dict[str, Any]) -> str | None:
    data_platform = role_profiles.get("data_platform", {})
    data_ai = role_profiles.get("data_ai", {})
    data_platform_keywords = [str(keyword) for keyword in data_platform.get("specialization_keywords", [])]
    data_ai_keywords = [str(keyword) for keyword in data_ai.get("specialization_keywords", [])]
    data_platform_anchor_keywords = [str(keyword) for keyword in data_platform.get("specialization_anchor_keywords", [])]
    data_ai_anchor_keywords = [str(keyword) for keyword in data_ai.get("specialization_anchor_keywords", [])]
    if not data_platform_keywords or not data_ai_keywords:
        return None

    data_platform_score = _count_matches(job_text, data_platform_keywords)
    data_ai_score = _count_matches(job_text, data_ai_keywords)
    score_margin = abs(data_platform_score - data_ai_score)
    if score_margin < 2:
        data_platform_anchor_score = _count_matches(job_text, data_platform_anchor_keywords)
        data_ai_anchor_score = _count_matches(job_text, data_ai_anchor_keywords)
        anchor_margin = abs(data_platform_anchor_score - data_ai_anchor_score)
        if score_margin == 1 and anchor_margin >= 1:
            if data_platform_anchor_score > data_ai_anchor_score:
                return "data_platform"
            if data_ai_anchor_score > data_platform_anchor_score:
                return "data_ai"
        if score_margin == 0 and anchor_margin >= 2:
            if data_platform_anchor_score > data_ai_anchor_score:
                return "data_platform"
            if data_ai_anchor_score > data_platform_anchor_score:
                return "data_ai"
        return None
    if data_platform_score > data_ai_score:
        return "data_platform"
    if data_ai_score > data_platform_score:
        return "data_ai"
    return None


def _describe_domain_selection(
    candidates: list[DomainCandidateScore],
    selected_domain: str | None,
    *,
    unsupported_role_family: str | None = None,
) -> str:
    if unsupported_role_family:
        return f"Skipped because unsupported role family guard forced General fallback ({unsupported_role_family})."
    if not candidates:
        return "No eligible domain candidates."

    top_candidate = candidates[0]
    if selected_domain is None:
        return (
            f"General fallback because best domain {top_candidate.label} reached "
            f"total={top_candidate.total_score} ratio={top_candidate.total_ratio:.2f}, below minimum signal threshold."
        )

    selected_candidate = next((candidate for candidate in candidates if candidate.domain_key == selected_domain), top_candidate)
    if selected_candidate.domain_key != top_candidate.domain_key:
        return f"{selected_candidate.label} selected after platform/data near-tie tie-break over {top_candidate.label}."

    if len(candidates) == 1:
        return f"{selected_candidate.label} was the only eligible domain candidate."

    second_candidate = candidates[1]
    near_tie = {selected_candidate.domain_key, second_candidate.domain_key} == {"platform", "data"} and abs(
        selected_candidate.total_score - second_candidate.total_score
    ) <= 1
    if near_tie:
        return (
            f"{selected_candidate.label} selected on total-signal lead over {second_candidate.label}; "
            "tie-break override was not needed."
        )
    return f"{selected_candidate.label} selected by total-signal ranking over {second_candidate.label}."


def _describe_role_selection(
    candidates: list[RoleCandidateScore],
    selected_role_profile: dict[str, Any] | None,
    *,
    unsupported_role_family: str | None = None,
) -> str:
    if unsupported_role_family:
        return f"Unsupported role family guard forced General fallback ({unsupported_role_family})."
    if not candidates:
        return "No eligible role candidates after domain filtering."

    best_candidate = candidates[0]
    if selected_role_profile is None:
        return (
            f"General fallback because best role {best_candidate.role_name} matched "
            f"{best_candidate.total_score}/{best_candidate.keyword_total} keywords "
            f"(ratio={best_candidate.match_ratio:.2f} < 0.20)."
        )
    if best_candidate.preferred_match:
        return (
            f"{best_candidate.role_name} selected because preferred specialization matched; "
            "preferred candidates are ranked ahead of anchor/signal/ratio within the selected domain."
        )
    if len(candidates) == 1:
        return f"{best_candidate.role_name} was the only eligible role candidate in the selected domain."

    second_candidate = candidates[1]
    return f"{best_candidate.role_name} selected by anchor/signal/ratio ranking over {second_candidate.role_name}."


def _select_role_profile(
    job_text: str,
    target_roles: list[dict[str, Any]],
    role_profiles: dict[str, Any],
    *,
    allowed_domain: str | None = None,
    preferred_profile_key: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, list[RoleCandidateScore]]:
    if not target_roles or not role_profiles:
        return None, None, []

    candidates: list[RoleCandidateScore] = []
    for index, target_role in enumerate(target_roles):
        role_key = _infer_role_profile_key(target_role, role_profiles)
        if role_key is None:
            continue
        role_profile = role_profiles.get(role_key, {})
        if allowed_domain and role_profile.get("domain") != allowed_domain:
            continue
        anchor_keywords = [str(keyword) for keyword in role_profile.get("selection_anchor_keywords", [])]
        signal_keywords = [str(keyword) for keyword in role_profile.get("selection_signal_keywords", [])]
        selection_keywords = _unique_keywords(
            _role_terms(target_role),
            [str(keyword) for keyword in role_profile.get("match_keywords", [])],
        )
        selection_score = _count_matches(job_text, selection_keywords)
        selection_total = len(selection_keywords)
        selection_ratio = selection_score / selection_total if selection_total else 0.0
        candidates.append(
            RoleCandidateScore(
                role_name=str(target_role.get("name", role_key)),
                profile_key=role_key,
                preferred_match=bool(preferred_profile_key and role_key == preferred_profile_key),
                anchor_score=_count_matches(job_text, anchor_keywords),
                signal_score=_count_matches(job_text, signal_keywords),
                total_score=selection_score,
                keyword_total=selection_total,
                match_ratio=selection_ratio,
                target_order=index,
            )
        )

    if not candidates:
        return None, None, []

    ranked_candidates = sorted(
        candidates,
        key=lambda item: (
            1 if item.preferred_match else 0,
            item.anchor_score,
            item.signal_score,
            item.total_score,
            item.match_ratio,
            -item.target_order,
        ),
        reverse=True,
    )
    selected_candidate = ranked_candidates[0]
    if selected_candidate.total_score <= 0 or selected_candidate.match_ratio < 0.2:
        return None, None, ranked_candidates

    selected_profile = role_profiles.get(selected_candidate.profile_key, {})
    return selected_profile, selected_candidate.role_name, ranked_candidates


def score_job_file(
    job_path: str | Path,
    *,
    report_path: Path | None = None,
    tracker_path: Path | None = None,
    report_dir: Path | None = None,
    tracker_dir: Path | None = None,
    profile_path: str | Path = "config/profile.yml",
    scorecard_path: str | Path = "config/scorecard.kr.yml",
    write_tracker: bool = True,
) -> ScoreJobArtifacts:
    try:
        target_job_path = Path(job_path)
        profile = load_yaml(profile_path)
        scorecard = load_yaml(scorecard_path)
        metadata, content = parse_front_matter(target_job_path)
        lower = content.lower()
        title_text = str(metadata.get("title") or target_job_path.stem).lower()
        role_profiles = scorecard.get("role_profiles", {})
        domains = scorecard.get("domains", {})
        unsupported_role_family = _detect_unsupported_role_family(
            title_text,
            scorecard["rules"].get("unsupported_role_family_keywords", {}),
        )
        if unsupported_role_family:
            selected_domain = None
            selected_specialization = None
            selected_domain_label = "General"
            selected_role_profile = None
            selected_role_name = None
            domain_candidate_scores: list[DomainCandidateScore] = []
            role_candidate_scores: list[RoleCandidateScore] = []
        else:
            selected_domain, domain_candidate_scores = _select_role_domain(
                lower,
                profile.get("target_roles", []),
                role_profiles,
                domains,
            )
            selected_specialization = _select_data_specialization(lower, role_profiles) if selected_domain == "data" else None
            selected_domain_label = domains.get(selected_domain, {}).get("label", "General") if selected_domain else "General"

            selected_role_profile, selected_role_name, role_candidate_scores = _select_role_profile(
                lower,
                profile.get("target_roles", []),
                role_profiles,
                allowed_domain=selected_domain,
                preferred_profile_key=selected_specialization,
            )
        selected_role_label = selected_role_profile.get("label", "General") if selected_role_profile else "General"
        selected_weights = selected_role_profile.get("weights", scorecard["weights"]) if selected_role_profile else scorecard["weights"]
        selected_stack_keywords = selected_role_profile.get("stack_keywords", []) if selected_role_profile else []
        all_skills = _unique_keywords(
            [str(skill) for skill in profile["skills"].get("primary", []) + profile["skills"].get("secondary", [])],
            [str(keyword) for keyword in selected_stack_keywords],
        )
        selected_target_role_name = selected_role_name or "General"
        selected_target_role = None
        if selected_role_name:
            selected_target_role = next(
                (role for role in profile.get("target_roles", []) if role.get("name", "") == selected_target_role_name),
                None,
            )
        role_keywords = _unique_keywords(
            _role_terms(selected_target_role or {}),
            [str(keyword) for keyword in selected_role_profile.get("match_keywords", [])] if selected_role_profile else [],
        )

        role_matches = _count_matches(lower, role_keywords)
        stack_matches = _count_matches(lower, all_skills)
        role_score = 1.0 if not role_keywords else _score_by_ratio(role_matches, len(role_keywords))
        stack_score = _score_by_ratio(stack_matches, len(all_skills))

        seniority = _detect_seniority(lower, scorecard["rules"]["seniority_keywords"])
        preferred_senior = "senior" if "senior" in selected_target_role_name.lower() else "mid"
        if seniority == preferred_senior:
            seniority_score = 5.0
        elif {seniority, preferred_senior} == {"mid", "senior"}:
            seniority_score = 4.0
        else:
            seniority_score = 3.0

        work_mode = _detect_work_mode(lower, scorecard["rules"]["work_mode_keywords"])
        preferred_modes = profile["preferences"]["work_modes"].get("preferred", [])
        acceptable_modes = profile["preferences"]["work_modes"].get("acceptable", [])
        if work_mode in preferred_modes:
            work_mode_score = 5.0
        elif work_mode in acceptable_modes:
            work_mode_score = 3.0
        elif work_mode == "unknown":
            work_mode_score = 3.0
        else:
            work_mode_score = 2.0

        language_needs = _detect_language_need(lower, scorecard["rules"]["language_keywords"])
        preferred_languages = profile["preferences"].get("preferred_languages", ["ko"])
        language_score = 5.0 if any(lang in preferred_languages for lang in language_needs) else 2.0

        compensation_signal = _detect_compensation_signal(lower)

        preferred_domains = profile["signals"].get("preferred_domains", [])
        avoid_domains = profile["signals"].get("avoid_domains", [])
        role_positive_company_keywords = (
            [str(keyword) for keyword in selected_role_profile.get("positive_company_keywords", [])]
            if selected_role_profile
            else []
        )
        role_negative_company_keywords = (
            [str(keyword) for keyword in selected_role_profile.get("negative_company_keywords", [])]
            if selected_role_profile
            else []
        )
        preferred_domain_matches = _count_matches(lower, preferred_domains)
        avoid_domain_matches = _count_matches(lower, avoid_domains)
        role_positive_company_matches = _count_matches(lower, role_positive_company_keywords)
        role_negative_company_matches = _count_matches(lower, role_negative_company_keywords)
        positive_company_matches = preferred_domain_matches + role_positive_company_matches
        negative_company_matches = avoid_domain_matches + role_negative_company_matches
        if positive_company_matches >= 2 and negative_company_matches == 0:
            company_signal = 5.0
        elif positive_company_matches >= 1 and negative_company_matches == 0:
            company_signal = 4.0
        elif negative_company_matches >= 1 and positive_company_matches == 0:
            company_signal = 1.0
        elif negative_company_matches >= 1:
            company_signal = 2.0
        else:
            company_signal = 3.0

        scores = {
            "role_alignment": role_score,
            "stack_overlap": stack_score,
            "seniority_fit": seniority_score,
            "work_mode_fit": work_mode_score,
            "language_fit": language_score,
            "compensation_signal": compensation_signal,
            "company_signal": company_signal,
        }
        total_score = _weighted_average(scores, selected_weights)

        company = _company_from_metadata(metadata)
        title = title_case(metadata.get("title")) if metadata.get("title") else title_case(target_job_path.stem)
        date = datetime.now(UTC).date().isoformat()
        slug = slugify(f"{company}-{title}", fallback="report")
        resolved_report_path = report_path or (report_dir or Path("reports")) / f"{date}-{slug}.md"
        resolved_tracker_path = None
        if write_tracker:
            resolved_tracker_path = tracker_path or (tracker_dir or Path("data/tracker-additions")) / f"{date}-{slug}.tsv"
        recommendation = "지원 적극 검토" if total_score >= 4.0 else "선별 검토" if total_score >= 3.0 else "스킵 권장"
    except Exception as exc:  # pragma: no cover - CLI-level smoke tests exercise this path.
        raise ScoreJobError(f"Failed to score {job_path}: {exc}") from exc

    score_lines = [
        "| Dimension | Weight | Score |",
        "|-----------|--------|-------|",
        *[
            f"| {key} | {weight} | {scores[key]:.1f} |"
            for key, weight in selected_weights.items()
        ],
    ]

    role_candidate_lines = (
        [
            (
                f"{candidate.role_name}: total={candidate.total_score}/{candidate.keyword_total} "
                f"ratio={candidate.match_ratio:.2f} "
                f"(anchor={candidate.anchor_score}, signal={candidate.signal_score}, "
                f"preferred={'yes' if candidate.preferred_match else 'no'})"
            )
            for candidate in role_candidate_scores
        ]
        if role_candidate_scores
        else ["N/A"]
    )
    domain_candidate_lines = (
        [
            (
                f"{candidate.label}: total={candidate.total_score} "
                f"(anchor={candidate.anchor_score}, signal={candidate.signal_score}, tie={candidate.tie_break_score})"
            )
            for candidate in domain_candidate_scores
        ]
        if domain_candidate_scores
        else ["N/A"]
    )
    domain_selection_note = _describe_domain_selection(
        domain_candidate_scores,
        selected_domain,
        unsupported_role_family=unsupported_role_family,
    )
    role_selection_note = _describe_role_selection(
        role_candidate_scores,
        selected_role_profile,
        unsupported_role_family=unsupported_role_family,
    )

    report = "\n".join(
        [
            f"# {company} - {title}",
            "",
            "## Summary",
            "",
            f"- Date: {date}",
            f"- Source: {metadata.get('source', 'manual')}",
            f"- URL: {metadata.get('url', 'N/A')}",
            f"- Selected Domain: {selected_domain_label}",
            f"- Domain Selection Note: {domain_selection_note}",
            f"- Selected Target Role: {selected_target_role_name}",
            f"- Selected Role Profile: {selected_role_label}",
            f"- Role Selection Note: {role_selection_note}",
            *( [f"- Unsupported Role Family: {unsupported_role_family}"] if unsupported_role_family else [] ),
            f"- Total Score: {total_score}/5",
            f"- Recommendation: {recommendation}",
            f"- Seniority Signal: {seniority}",
            f"- Work Mode Signal: {work_mode}",
            f"- Language Signal: {', '.join(language_needs)}",
            f"- Domain Match Candidates: {', '.join(domain_candidate_lines)}",
            f"- Role Match Candidates: {', '.join(role_candidate_lines)}",
            "",
            "## Scorecard",
            "",
            *score_lines,
            "",
            "## Why It Fits",
            "",
            f"- Role keyword overlap: {role_matches}/{len(role_keywords)}",
            f"- Stack keyword overlap: {stack_matches}/{len(all_skills)}",
            f"- Preferred domains matched: {preferred_domain_matches}",
            f"- Role-specific positive company signals: {role_positive_company_matches}",
            "",
            "## Risks",
            "",
            f"- Avoid-domain matches: {avoid_domain_matches}",
            f"- Role-specific negative company signals: {role_negative_company_matches}",
            f"- Compensation disclosed: {'yes' if compensation_signal >= 4 else 'no clear signal'}",
            f"- Work mode confidence: {'low' if work_mode == 'unknown' else 'medium'}",
            "",
            "## Manual Review Notes",
            "",
            "- 한국 개발자 관점에서 출근 빈도와 팀 구조를 확인할 것",
            "- JD에 없는 연봉, 평가 방식, 인터뷰 단계는 추가 조사 필요",
            "- Codex가 정성 평가와 이력서 커스텀 포인트를 여기에 보강할 수 있음",
            "",
        ]
    )

    tracker_row = (
        "\t".join(
            [
                date,
                company,
                title,
                f"{total_score}/5",
                "검토중",
                str(metadata.get("source", "manual")),
                "",
                resolved_report_path.as_posix(),
                recommendation,
            ]
        )
        + "\n"
    )
    written_paths: list[Path] = []
    try:
        ensure_dir(resolved_report_path.parent)
        resolved_report_path.write_text(report, encoding="utf-8")
        written_paths.append(resolved_report_path)
        if resolved_tracker_path:
            ensure_dir(resolved_tracker_path.parent)
            resolved_tracker_path.write_text(tracker_row, encoding="utf-8")
            written_paths.append(resolved_tracker_path)
    except Exception as exc:  # pragma: no cover - CLI-level smoke tests exercise this path.
        for path in written_paths:
            if path.exists():
                path.unlink()
        raise ScoreJobError(f"Failed to write scoring outputs for {job_path}: {exc}") from exc

    return ScoreJobArtifacts(
        report_path=resolved_report_path,
        tracker_path=resolved_tracker_path,
        total_score=total_score,
        recommendation=recommendation,
    )
