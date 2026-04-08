from __future__ import annotations

from pathlib import Path

from career_ops_kr.research import (
    COMPANY_RESEARCH_PROMPT_PATH,
    create_company_research_brief,
    create_company_research_followup,
)


def run_prepare_company_research(
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
    return create_company_research_brief(
        company_name,
        out=out,
        homepage=homepage,
        careers_url=careers_url,
        job_url=job_url,
        jobplanet_url=jobplanet_url,
        blind_url=blind_url,
        job_path=job_path,
        report_path=report_path,
        extra_sources=extra_sources or [],
        prompt_path=prompt_path,
        overwrite=overwrite,
    )


def run_prepare_company_followup(
    research_path: Path,
    *,
    mode: str,
    out: Path | None = None,
    overwrite: bool = False,
) -> Path:
    return create_company_research_followup(
        research_path,
        mode=mode,
        out=out,
        overwrite=overwrite,
    )
