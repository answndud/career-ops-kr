from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from career_ops_kr.portals import (
    DEFAULT_HEADERS,
    canonicalize_job_url,
    is_indeed_url,
    is_rocketpunch_url,
    is_supported_indeed_detail_url,
    is_supported_rocketpunch_detail_url,
)
from career_ops_kr.utils import ensure_dir, slugify


def fetch_job_to_markdown(
    url: str,
    *,
    out: Path | None = None,
    output_dir: Path | None = None,
    source: str = "manual",
    insecure: bool = False,
) -> Path:
    normalized_url = canonicalize_job_url(url)
    if is_indeed_url(normalized_url) and not is_supported_indeed_detail_url(normalized_url):
        raise ValueError(
            "Indeed intake supports manual detail URLs only. Use /viewjob?jk=<job_key> URLs, not search or company listing pages."
        )
    if is_rocketpunch_url(normalized_url) and not is_supported_rocketpunch_detail_url(normalized_url):
        raise ValueError(
            "RocketPunch intake supports manual detail URLs only. Use /jobs/<job_id> detail URLs, not listing or company recruit pages."
        )

    try:
        response = httpx.get(
            normalized_url,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
            verify=not insecure,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        message = f"Failed to fetch {normalized_url}: {exc}"
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            message += " | Retry with --insecure if this is a local certificate issue."
        raise ValueError(message) from exc

    html = response.text
    structured_job = _extract_structured_job_posting(html)
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, flags=re.IGNORECASE)
    fallback_title = (
        title_match.group(1).strip()
        if title_match
        else Path(httpx.URL(normalized_url).path).name or "Untitled Job"
    )
    title = structured_job.get("title") or fallback_title
    company = structured_job.get("company")
    text = structured_job.get("text") or _extract_main_text(html)
    if _is_rocketpunch_gate_content(normalized_url, text, html=html):
        raise ValueError(
            "RocketPunch returned login or anti-crawl gate content instead of a usable job detail page. Keep RocketPunch as a manual reference source for now."
        )
    language = _detect_language(text)
    fetched_at = datetime.now(UTC).isoformat()
    date = fetched_at[:10]
    default_dir = output_dir or Path("jds")
    output_path = out or default_dir / f"{date}-{slugify(title, fallback='job-post')}.md"

    ensure_dir(output_path.parent)
    body = (
        "---\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"company: {json.dumps(company, ensure_ascii=False)}\n"
        f"url: {json.dumps(normalized_url, ensure_ascii=False)}\n"
        f"source: {json.dumps(source, ensure_ascii=False)}\n"
        f"fetched_at: {json.dumps(fetched_at, ensure_ascii=False)}\n"
        f"language: {json.dumps(language, ensure_ascii=False)}\n"
        "---\n\n"
        f"# {title}\n\n{text}\n"
    )
    output_path.write_text(body, encoding="utf-8")
    return output_path


def _extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script, style, noscript, svg"):
        node.decompose()

    container = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )
    text = container.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_structured_job_posting(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", {"type": re.compile("json", re.IGNORECASE)}):
        raw = (script.get_text() or "").strip()
        if not raw:
            continue
        for payload in _load_json_candidates(raw):
            job_posting = _find_job_posting(payload)
            if not job_posting:
                continue
            title = str(job_posting.get("title") or "").strip()
            company = _extract_job_posting_company(job_posting)
            text = _build_job_posting_text(job_posting)
            if title or text:
                return {
                    "title": title,
                    "company": company,
                    "text": text,
                }
    return {}


def _load_json_candidates(raw: str) -> list[Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return payload
    return [payload]


def _find_job_posting(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if str(payload.get("@type", "")).lower() == "jobposting":
            return payload
        for value in payload.values():
            job_posting = _find_job_posting(value)
            if job_posting:
                return job_posting
    elif isinstance(payload, list):
        for item in payload:
            job_posting = _find_job_posting(item)
            if job_posting:
                return job_posting
    return None


def _extract_job_posting_company(job_posting: dict[str, Any]) -> str:
    organization = job_posting.get("hiringOrganization")
    if isinstance(organization, dict):
        return str(organization.get("name") or "").strip()
    return ""


def _build_job_posting_text(job_posting: dict[str, Any]) -> str:
    sections: list[tuple[str, str]] = []
    description = str(job_posting.get("description") or "").strip()
    qualifications = str(job_posting.get("qualifications") or "").strip()
    experience = str(job_posting.get("experienceRequirements") or "").strip()
    responsibilities = str(job_posting.get("responsibilities") or "").strip()

    if description:
        sections.append(("Description", description))
    if qualifications:
        sections.append(("Qualifications", qualifications))
    if responsibilities:
        sections.append(("Responsibilities", responsibilities))
    if experience:
        sections.append(("Experience", experience))

    lines: list[str] = []
    for heading, value in sections:
        normalized = value.replace("\\n", "\n")
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
        if not normalized:
            continue
        lines.extend([heading, normalized, ""])
    return "\n".join(lines).strip()


def _detect_language(text: str) -> str:
    sample = text[:3000]
    hangul_count = len(re.findall(r"[가-힣]", sample))
    return "ko" if sample and hangul_count > len(sample) * 0.03 else "en"


def _is_rocketpunch_gate_content(url: str, text: str, *, html: str | None = None) -> bool:
    try:
        host = (httpx.URL(url).host or "").lower()
    except Exception:
        return False
    if host != "www.rocketpunch.com":
        return False

    anti_crawl_markers = [
        "개인정보 데이터를 포함하여 각 정보주체의 동의 없이 데이터를 무단으로 수집하는 행위를 금지",
        "공개된 데이터도 크롤링 등 기술적 장치를 이용해 허가 없이 수집",
        "로그인 후 검색 가능",
    ]
    if all(marker in text for marker in anti_crawl_markers):
        return True
    lowered_html = (html or "").lower()
    html_gate_markers = [
        "x-amzn-waf-action",
        "awswafcookiedomainlist",
        "window.gokuprops",
    ]
    if any(marker in lowered_html for marker in html_gate_markers):
        return True
    return len(text.strip()) < 80
