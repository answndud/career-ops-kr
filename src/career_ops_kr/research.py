from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

from career_ops_kr.utils import ensure_dir, parse_front_matter, slugify


JOBPLANET_COMPANIES_URL = "https://www.jobplanet.co.kr/companies"
BLIND_COMPANIES_URL = "https://www.teamblind.com/company/"
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPANY_RESEARCH_PROMPT_PATH = REPO_ROOT / "prompts" / "company-research.md"
FOLLOWUP_MODES = {"summary", "outreach"}


def _load_research_items(prompt_path: str | Path) -> list[str]:
    items: list[str] = []
    for line in Path(prompt_path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"\d+\.\s+(.*)", line.strip())
        if match:
            items.append(match.group(1).strip())
    return items


def _default_research_items() -> list[str]:
    return [
        "제품과 비즈니스 모델",
        "기술 조직 구조 추정",
        "최근 6개월 내 채용/투자/제품 변화",
        "개발자 관점의 강점과 리스크",
        "면접에서 물어볼 질문 5개",
    ]


def _parse_extra_sources(extra_sources: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for raw in extra_sources:
        label, sep, url = raw.partition("=")
        if not sep or not label.strip() or not url.strip():
            raise ValueError(f"Invalid extra source '{raw}'. Use LABEL=URL format.")
        parsed.append((label.strip(), url.strip()))
    return parsed


def _build_notes_sections(research_items: list[str]) -> list[str]:
    lines: list[str] = ["## Notes", ""]
    for index, item in enumerate(research_items, start=1):
        lines.extend([f"### {index}. {item}", ""])
        if "질문" in item:
            lines.extend(["1. TODO", "2. TODO", "3. TODO", "4. TODO", "5. TODO", ""])
        else:
            lines.extend(["- TODO", ""])
    return lines


def _build_company_search_hints(company: str) -> list[str]:
    encoded_company = quote_plus(company)
    return [
        f"- JobPlanet search query: site:jobplanet.co.kr/companies \"{company}\"",
        f"- JobPlanet search URL: https://www.google.com/search?q={quote_plus(f'site:jobplanet.co.kr/companies \"{company}\"')}",
        f"- Blind search query: site:teamblind.com/company \"{company}\"",
        f"- Blind search URL: https://www.google.com/search?q={quote_plus(f'site:teamblind.com/company \"{company}\"')}",
        f"- Broad company query URL: https://www.google.com/search?q={encoded_company}",
        "- Manual note: if the company has a Korean and English name, try both spellings before fixing the exact page URL.",
    ]


def create_company_research_brief(
    company_name: str,
    *,
    out: Path | None = None,
    homepage: str | None = None,
    careers_url: str | None = None,
    job_url: str | None = None,
    jobplanet_url: str | None = None,
    blind_url: str | None = None,
    job_path: Path | None = None,
    report_path: Path | None = None,
    extra_sources: list[str] | None = None,
    prompt_path: Path = COMPANY_RESEARCH_PROMPT_PATH,
    overwrite: bool = False,
) -> Path:
    company = company_name.strip()
    if not company:
        raise ValueError("Company name must not be empty.")

    created_at = datetime.now(UTC).isoformat()
    date = created_at[:10]
    output_path = out or Path("research") / f"{date}-{slugify(company, fallback='company-research')}.md"
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Research brief already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )
    if job_path and not job_path.exists():
        raise ValueError(f"Job markdown path does not exist: {job_path.as_posix()}")
    if report_path and not report_path.exists():
        raise ValueError(f"Report path does not exist: {report_path.as_posix()}")

    research_items = _load_research_items(prompt_path)
    if not research_items:
        research_items = _default_research_items()
    parsed_extra_sources = _parse_extra_sources(extra_sources or [])
    ensure_dir(output_path.parent)

    front_matter_lines = [
        "---",
        f"company: {json.dumps(company, ensure_ascii=False)}",
        f"created_at: {json.dumps(created_at, ensure_ascii=False)}",
        f"homepage: {json.dumps(homepage, ensure_ascii=False)}",
        f"careers_url: {json.dumps(careers_url, ensure_ascii=False)}",
        f"job_url: {json.dumps(job_url, ensure_ascii=False)}",
        f"jobplanet_url: {json.dumps(jobplanet_url, ensure_ascii=False)}",
        f"blind_url: {json.dumps(blind_url, ensure_ascii=False)}",
        f"job_path: {json.dumps(job_path.as_posix() if job_path else None, ensure_ascii=False)}",
        f"report_path: {json.dumps(report_path.as_posix() if report_path else None, ensure_ascii=False)}",
        f"prompt_path: {json.dumps(prompt_path.as_posix(), ensure_ascii=False)}",
        "---",
        "",
    ]

    official_sources = [
        f"- Homepage: {homepage or 'TBD'}",
        f"- Careers: {careers_url or 'TBD'}",
        f"- Target job URL: {job_url or 'TBD'}",
        f"- JD Markdown: {job_path.as_posix() if job_path else 'TBD'}",
        f"- Score Report: {report_path.as_posix() if report_path else 'TBD'}",
    ]
    research_sources = [
        f"- JobPlanet page: {jobplanet_url or 'TBD'}",
        f"- JobPlanet browse: {JOBPLANET_COMPANIES_URL}",
        f"- Blind page: {blind_url or 'TBD'}",
        f"- Blind browse: {BLIND_COMPANIES_URL}",
        f"- Search note: Search `{company}` in JobPlanet/Blind UI if exact company URLs are not known yet.",
        "- Manual workflow note: do not add JobPlanet or Blind to automated job discovery.",
    ]
    for label, url in parsed_extra_sources:
        research_sources.append(f"- {label}: {url}")

    checklist_lines = [f"{index}. {item}" for index, item in enumerate(research_items, start=1)]

    body = "\n".join(
        front_matter_lines
        + [
            f"# {company} Research Brief",
            "",
            "## Official Sources",
            "",
            *official_sources,
            "",
            "## Research Sources",
            "",
            *research_sources,
            "",
            "## Search Hints",
            "",
            *_build_company_search_hints(company),
            "",
            "## Research Checklist",
            "",
            *checklist_lines,
            "",
            *_build_notes_sections(research_items),
            "## Source Attribution Rules",
            "",
            "- 각 사실 옆에 출처를 남긴다.",
            "- 확실하지 않은 내용은 추정이라고 표시한다.",
            "- JobPlanet/Blind에서 최종 회사 페이지 URL을 찾았으면 이 문서의 Research Sources를 먼저 갱신한다.",
            "",
        ]
    )

    output_path.write_text(body, encoding="utf-8")
    return output_path


def create_company_research_followup(
    brief_path: Path,
    *,
    mode: str = "summary",
    out: Path | None = None,
    overwrite: bool = False,
) -> Path:
    if not brief_path.exists():
        raise ValueError(f"Research brief does not exist: {brief_path.as_posix()}")

    normalized_mode = mode.strip().lower()
    if normalized_mode not in FOLLOWUP_MODES:
        supported = ", ".join(sorted(FOLLOWUP_MODES))
        raise ValueError(f"Unsupported follow-up mode: {mode}. Supported: {supported}")

    metadata, _body = parse_front_matter(brief_path)
    company = str(metadata.get("company") or brief_path.stem).strip()
    if not company:
        raise ValueError(f"Could not determine company name from research brief: {brief_path.as_posix()}")

    created_at = datetime.now(UTC).isoformat()
    date = created_at[:10]
    output_path = out or brief_path.parent / f"{date}-{slugify(company, fallback='company')}-{normalized_mode}.md"
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"Research follow-up already exists: {output_path.as_posix()} | Use --overwrite to replace it."
        )

    prompt_path = metadata.get("prompt_path")
    research_items: list[str] = []
    if prompt_path:
        try:
            research_items = _load_research_items(str(prompt_path))
        except OSError:
            research_items = []
    if not research_items:
        research_items = _default_research_items()

    ensure_dir(output_path.parent)
    body = "\n".join(
        [
            "---",
            f"company: {json.dumps(company, ensure_ascii=False)}",
            f"created_at: {json.dumps(created_at, ensure_ascii=False)}",
            f"mode: {json.dumps(normalized_mode, ensure_ascii=False)}",
            f"source_brief: {json.dumps(brief_path.as_posix(), ensure_ascii=False)}",
            f"homepage: {json.dumps(metadata.get('homepage'), ensure_ascii=False)}",
            f"careers_url: {json.dumps(metadata.get('careers_url'), ensure_ascii=False)}",
            f"job_url: {json.dumps(metadata.get('job_url'), ensure_ascii=False)}",
            f"jobplanet_url: {json.dumps(metadata.get('jobplanet_url'), ensure_ascii=False)}",
            f"blind_url: {json.dumps(metadata.get('blind_url'), ensure_ascii=False)}",
            f"job_path: {json.dumps(metadata.get('job_path'), ensure_ascii=False)}",
            f"report_path: {json.dumps(metadata.get('report_path'), ensure_ascii=False)}",
            "---",
            "",
            f"# {company} {'Research Summary' if normalized_mode == 'summary' else 'Outreach Draft'}",
            "",
            "## Input Sources",
            "",
            f"- Research brief: {brief_path.as_posix()}",
            f"- Homepage: {metadata.get('homepage') or 'TBD'}",
            f"- Careers: {metadata.get('careers_url') or 'TBD'}",
            f"- Target job URL: {metadata.get('job_url') or 'TBD'}",
            f"- JobPlanet page: {metadata.get('jobplanet_url') or 'TBD'}",
            f"- Blind page: {metadata.get('blind_url') or 'TBD'}",
            f"- JD Markdown: {metadata.get('job_path') or 'TBD'}",
            f"- Score Report: {metadata.get('report_path') or 'TBD'}",
            "",
            "## Research Prompts To Reuse",
            "",
            *[f"- {item}" for item in research_items],
            "",
        ]
        + (
            [
                "## Summary Draft",
                "",
                "### 회사 한 줄 요약",
                "",
                "- TODO",
                "",
                "### 개발자 관점 핵심 신호",
                "",
                "- TODO",
                "- TODO",
                "- TODO",
                "",
                "### 리스크와 확인 필요 사항",
                "",
                "- TODO",
                "- TODO",
                "- TODO",
                "",
                "### 다음 액션",
                "",
                "- TODO",
                "",
            ]
            if normalized_mode == "summary"
            else [
                "## Outreach Drafts",
                "",
                "### Recruiter Outreach",
                "",
                "- Hook: TODO",
                "- Draft: TODO",
                "",
                "### Hiring Manager Note",
                "",
                "- Hook: TODO",
                "- Draft: TODO",
                "",
                "### Referral Request",
                "",
                "- Hook: TODO",
                "- Draft: TODO",
                "",
                "## Messaging Constraints",
                "",
                "- Research brief의 확인된 사실만 사용한다.",
                "- 추정은 명시적으로 표시한다.",
                "- tracker나 pipeline 상태를 이 문서에서 변경하지 않는다.",
                "",
            ]
        )
        + [
            "## Source Attribution Rules",
            "",
            "- 최종 문안이나 요약에 들어가는 사실은 research brief에서 출처를 다시 확인한다.",
            "- 확실하지 않은 내용은 추정이라고 표시한다.",
            "- 이 문서는 intake나 tracker 변경 명령이 아니라 follow-up draft scaffold다.",
            "",
        ]
    )
    output_path.write_text(body, encoding="utf-8")
    return output_path
