from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import httpx

from career_ops_kr.utils import ensure_dir


DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
}

SARAMIN_API_URL = "https://oapi.saramin.co.kr/job-search"
SARAMIN_DEFAULT_JOB_MID_CD = "2"
SARAMIN_MAX_COUNT = 110


@dataclass(frozen=True)
class PortalSpec:
    sitemap_index: str
    child_sitemap_pattern: re.Pattern[str]
    detail_url_pattern: re.Pattern[str]
    canonical_template: str


PORTAL_SPECS: dict[str, PortalSpec] = {
    "wanted": PortalSpec(
        sitemap_index="https://www.wanted.co.kr/sitemap.xml",
        child_sitemap_pattern=re.compile(r"sitemap_kr_job_\d+\.xml$"),
        detail_url_pattern=re.compile(r"/wd/(?P<job_id>\d+)$"),
        canonical_template="https://www.wanted.co.kr/wd/{job_id}",
    ),
    "jumpit": PortalSpec(
        sitemap_index="https://jumpit.saramin.co.kr/sitemap.xml",
        child_sitemap_pattern=re.compile(r"sitemap_position_view_\d+\.xml$"),
        detail_url_pattern=re.compile(r"/position/(?P<job_id>\d+)$"),
        canonical_template="https://jumpit.saramin.co.kr/position/{job_id}",
    ),
    "remember": PortalSpec(
        sitemap_index="https://career.rememberapp.co.kr/sitemap.xml",
        child_sitemap_pattern=re.compile(r"sitemap-jobs\.xml$"),
        detail_url_pattern=re.compile(r"/job/posting/(?P<job_id>\d+)$"),
        canonical_template="https://career.rememberapp.co.kr/job/posting/{job_id}",
    ),
}

ROCKETPUNCH_DETAIL_RE = re.compile(
    r"(?:/[a-z]{2}(?:-[A-Z]{2})?)?/jobs/(?P<job_id>\d+)(?:/[^/?#]+)?/?$"
)


def supported_portals() -> list[str]:
    return sorted([*PORTAL_SPECS, "saramin"])


def canonicalize_job_url(url: str) -> str:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return url.strip()

    host = (parsed.host or "").lower()
    path = parsed.path or ""
    if host in {"www.wanted.co.kr", "recruit.wanted.co.kr"}:
        match = re.search(r"/wd/(?P<job_id>\d+)$", path)
        if match:
            return PORTAL_SPECS["wanted"].canonical_template.format(job_id=match.group("job_id"))

    if host == "jumpit.saramin.co.kr":
        match = re.search(r"/position/(?P<job_id>\d+)$", path)
        if match:
            return PORTAL_SPECS["jumpit"].canonical_template.format(job_id=match.group("job_id"))

    if host == "career.rememberapp.co.kr":
        match = re.search(r"/job/posting/(?P<job_id>\d+)$", path)
        if match:
            return PORTAL_SPECS["remember"].canonical_template.format(job_id=match.group("job_id"))
        posting_id = parsed.params.get("postingId")
        if path == "/job/postings" and posting_id and posting_id.isdigit():
            return PORTAL_SPECS["remember"].canonical_template.format(job_id=posting_id)

    if host == "www.saramin.co.kr" and path == "/zf_user/jobs/relay/view":
        rec_idx = parsed.params.get("rec_idx")
        if rec_idx and rec_idx.isdigit():
            return f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}"

    if is_supported_rocketpunch_detail_url(url):
        match = ROCKETPUNCH_DETAIL_RE.fullmatch(path)
        if match:
            return f"https://www.rocketpunch.com/jobs/{match.group('job_id')}"

    if is_supported_indeed_detail_url(url):
        job_key = _indeed_job_key(parsed)
        if job_key:
            return f"https://{_canonical_indeed_host(host)}/viewjob?jk={job_key}"

    return str(parsed)


def is_supported_indeed_detail_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False

    host = (parsed.host or "").lower()
    path = parsed.path or ""
    return _is_indeed_host(host) and path in {"/viewjob", "/m/viewjob"} and bool(_indeed_job_key(parsed))


def is_indeed_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False
    return _is_indeed_host((parsed.host or "").lower())


def is_supported_rocketpunch_detail_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False

    host = (parsed.host or "").lower()
    path = parsed.path or ""
    return host in {"rocketpunch.com", "www.rocketpunch.com"} and bool(ROCKETPUNCH_DETAIL_RE.fullmatch(path))


def is_rocketpunch_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False
    return (parsed.host or "").lower() in {"rocketpunch.com", "www.rocketpunch.com"}


def infer_source_from_url(url: str) -> str:
    try:
        parsed = httpx.URL(canonicalize_job_url(url))
    except Exception:
        return "manual"

    host = (parsed.host or "").lower()
    path = parsed.path or ""
    if host in {"www.wanted.co.kr", "recruit.wanted.co.kr"} and path.startswith("/wd/"):
        return "wanted"
    if host == "jumpit.saramin.co.kr" and path.startswith("/position/"):
        return "jumpit"
    if host == "career.rememberapp.co.kr" and path.startswith("/job/posting/"):
        return "remember"
    if host == "www.saramin.co.kr" and path == "/zf_user/jobs/relay/view" and parsed.params.get("rec_idx"):
        return "saramin"
    if host == "www.rocketpunch.com" and path.startswith("/jobs"):
        return "rocketpunch"
    if _is_indeed_host(host) and path == "/viewjob" and parsed.params.get("jk"):
        return "indeed"
    return "manual"


def discover_job_urls(source: str, *, limit: int, insecure: bool = False) -> list[str]:
    if source.lower() == "saramin":
        return _discover_saramin_job_urls(limit=limit, insecure=insecure)

    spec = PORTAL_SPECS.get(source.lower())
    if spec is None:
        supported = ", ".join(supported_portals())
        raise ValueError(f"Unsupported portal source: {source}. Supported: {supported}")

    urls: list[str] = []
    seen: set[str] = set()

    with httpx.Client(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30.0,
        verify=not insecure,
    ) as client:
        for sitemap_url in _iter_child_sitemaps(client, spec):
            for detail_url in _iter_detail_urls(client, sitemap_url, spec):
                if detail_url in seen:
                    continue
                seen.add(detail_url)
                urls.append(detail_url)
                if len(urls) >= limit:
                    return urls

    return urls


def merge_pending_urls(pipeline_path: str | Path, urls: list[str]) -> int:
    target = Path(pipeline_path)
    ensure_dir(target.parent)
    if not target.exists():
        target.write_text("# Pipeline Inbox\n\n## Pending\n\n## Processed\n", encoding="utf-8")

    lines = target.read_text(encoding="utf-8").splitlines()
    existing = {
        canonicalize_job_url(line[6:].strip())
        for line in lines
        if line.startswith("- [ ] ") or line.startswith("- [x] ")
    }
    new_urls: list[str] = []
    seen_new: set[str] = set()
    for url in urls:
        canonical_url = canonicalize_job_url(url)
        if canonical_url in existing or canonical_url in seen_new:
            continue
        seen_new.add(canonical_url)
        new_urls.append(canonical_url)
    if not new_urls:
        return 0

    insert_at = _find_pending_insert_index(lines)
    new_lines = [f"- [ ] {url}" for url in new_urls]

    updated_lines = list(lines)
    updated_lines[insert_at:insert_at] = new_lines + [""]
    target.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    return len(new_urls)


def _find_pending_insert_index(lines: list[str]) -> int:
    pending_header = None
    for index, line in enumerate(lines):
        if line.strip() == "## Pending":
            pending_header = index
            break

    if pending_header is None:
        lines.extend(["", "## Pending", ""])
        return len(lines)

    insert_at = pending_header + 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    while insert_at < len(lines) and lines[insert_at].startswith("- ["):
        insert_at += 1
    return insert_at


def _discover_saramin_job_urls(*, limit: int, insecure: bool) -> list[str]:
    access_key = os.environ.get("SARAMIN_ACCESS_KEY", "").strip()
    if not access_key:
        raise ValueError(
            "Saramin discovery requires SARAMIN_ACCESS_KEY. Apply for an access-key at https://oapi.saramin.co.kr/ and retry."
        )

    urls: list[str] = []
    seen: set[str] = set()
    start = 1

    with httpx.Client(
        headers={**DEFAULT_HEADERS, "accept": "application/json"},
        follow_redirects=True,
        timeout=30.0,
        verify=not insecure,
    ) as client:
        while len(urls) < limit:
            count = min(limit - len(urls), SARAMIN_MAX_COUNT)
            response = client.get(
                SARAMIN_API_URL,
                params={
                    "access-key": access_key,
                    "job_mid_cd": SARAMIN_DEFAULT_JOB_MID_CD,
                    "sr": "directhire",
                    "sort": "pd",
                    "start": str(start),
                    "count": str(count),
                },
            )
            response.raise_for_status()
            payload = response.json()
            _raise_for_saramin_error(payload)
            batch_urls = _extract_saramin_job_urls(payload)
            if not batch_urls:
                break
            for url in batch_urls:
                if url in seen:
                    continue
                seen.add(url)
                urls.append(url)
                if len(urls) >= limit:
                    break
            if len(batch_urls) < count:
                break
            start += 1

    return urls


def _iter_child_sitemaps(client: httpx.Client, spec: PortalSpec) -> list[str]:
    response = client.get(spec.sitemap_index)
    response.raise_for_status()
    sitemap_urls = _extract_loc_values(response.text)
    return [url for url in sitemap_urls if spec.child_sitemap_pattern.search(url)]


def _iter_detail_urls(client: httpx.Client, sitemap_url: str, spec: PortalSpec) -> list[str]:
    response = client.get(sitemap_url)
    response.raise_for_status()
    detail_urls: list[str] = []
    for candidate in _extract_loc_values(response.text):
        match = spec.detail_url_pattern.search(httpx.URL(candidate).path)
        if not match:
            continue
        detail_urls.append(spec.canonical_template.format(job_id=match.group("job_id")))
    return detail_urls


def _raise_for_saramin_error(payload: dict[str, object]) -> None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return
    code = result.get("code")
    message = result.get("message", "Unknown Saramin API error")
    raise ValueError(f"Saramin API error {code}: {message}")


def _extract_saramin_job_urls(payload: dict[str, object]) -> list[str]:
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        return []
    raw_job_items = jobs.get("job", [])
    if isinstance(raw_job_items, dict):
        raw_job_items = [raw_job_items]
    if not isinstance(raw_job_items, list):
        return []

    urls: list[str] = []
    for item in raw_job_items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        urls.append(canonicalize_job_url(url))
    return urls


def _extract_loc_values(xml_text: str) -> list[str]:
    root = ElementTree.fromstring(xml_text)
    values: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) == "loc" and node.text:
            values.append(node.text.strip())
    return values


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _is_indeed_host(host: str) -> bool:
    return host in {"indeed.com", "www.indeed.com", "m.indeed.com"} or host.endswith(".indeed.com")


def _canonical_indeed_host(host: str) -> str:
    if host in {"indeed.com", "www.indeed.com", "m.indeed.com"}:
        return "www.indeed.com"
    if host.startswith("m.") and host.endswith(".indeed.com"):
        return host[2:]
    return host


def _indeed_job_key(parsed: httpx.URL) -> str | None:
    job_key = parsed.params.get("jk") or parsed.params.get("vjk")
    return job_key.strip() if job_key else None
