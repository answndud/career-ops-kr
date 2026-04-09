from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from career_ops_kr.web.ai import translate_query


SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass(slots=True)
class JobSearchResult:
    id: str
    title: str
    company: str
    location: str
    source: str
    url: str
    type: str
    experience: str
    salary: str
    deadline: str
    description: str


@dataclass(slots=True)
class SearchProviderStatus:
    key: str
    label: str
    status: str
    tone: str
    count: int
    state_label: str
    detail: str
    query: str
    query_label: str
    message: str | None = None


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value or "")).strip()


def has_korean(text: str) -> bool:
    return bool(re.search(r"[\uAC00-\uD7AF\u1100-\u11FF]", text))


def _query_pair(query: str) -> tuple[str, str, str | None]:
    if has_korean(query):
        english = translate_query(query, target_language="en")
        return query, english, f"EN: {english}" if english != query else None
    korean = translate_query(query, target_language="ko")
    return korean, query, f"KR: {korean}" if korean != query else None


def _provider_query_label(original_query: str, provider_query: str) -> str:
    normalized_original = original_query.strip()
    normalized_provider = provider_query.strip()
    if normalized_provider == normalized_original:
        return "입력어"
    if has_korean(normalized_original) and not has_korean(normalized_provider):
        return "영문 번역"
    if not has_korean(normalized_original) and has_korean(normalized_provider):
        return "한글 번역"
    return "정규화 검색어"


def _provider_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "요청 시간 초과"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.RequestError):
        return "연결 실패"
    raw_message = str(exc).strip()
    return raw_message[:160] if raw_message else exc.__class__.__name__


def _provider_summary(provider_statuses: list[SearchProviderStatus]) -> dict[str, Any]:
    ok_count = sum(1 for item in provider_statuses if item.status == "ok")
    empty_count = sum(1 for item in provider_statuses if item.status == "empty")
    error_count = sum(1 for item in provider_statuses if item.status == "error")
    return {
        "total": len(provider_statuses),
        "responded": ok_count + empty_count,
        "ok": ok_count,
        "empty": empty_count,
        "error": error_count,
        "failed_labels": [item.label for item in provider_statuses if item.status == "error"],
        "empty_labels": [item.label for item in provider_statuses if item.status == "empty"],
        "summary": f"정상 {ok_count}개 · 결과 없음 {empty_count}개 · 실패 {error_count}개",
    }


def _search_efinancial(query: str) -> list[JobSearchResult]:
    url = "https://job-search-api.efinancialcareers.com/v1/efc/jobs/search"
    params = {"culture": "us", "q": query, "pageSize": 15, "page": 1}
    response = httpx.get(url, params=params, headers=SEARCH_HEADERS, timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    results: list[JobSearchResult] = []
    for index, item in enumerate(payload.get("data") or []):
        location = item.get("jobLocation") or {}
        city = str(location.get("city") or "")
        country = str(location.get("country") or "")
        location_label = ", ".join(part for part in [city, country] if part) or "-"
        results.append(
            JobSearchResult(
                id=f"efc-{item.get('id') or index}",
                title=str(item.get("title") or ""),
                company=str(item.get("companyName") or item.get("clientBrandName") or ""),
                location=location_label,
                source="eFinancial",
                url=(
                    f"https://www.efinancialcareers.com{item['detailsPageUrl']}"
                    if item.get("detailsPageUrl")
                    else ""
                ),
                type=str(item.get("employmentType") or "-"),
                experience="-",
                salary=str(item.get("salary") or "-"),
                deadline=str(item.get("postedDate") or "-")[:10],
                description=_strip_tags(str(item.get("summary") or ""))[:300],
            )
        )
    return results


def _search_saramin(query: str) -> list[JobSearchResult]:
    url = "https://www.saramin.co.kr/zf_user/search"
    params = {
        "searchword": query,
        "searchMode": "1",
        "searchType": "search",
        "search_done": "y",
        "search_optional_item": "n",
    }
    response = httpx.get(url, params=params, headers=SEARCH_HEADERS, timeout=30.0)
    response.raise_for_status()
    html = response.text
    blocks = html.split('class="area_job"')
    blocks.pop(0) if blocks else None
    results: list[JobSearchResult] = []
    for index, block in enumerate(blocks[:20]):
        title_match = re.search(
            r'class="job_tit"[\s\S]*?href="([^"]*)"[\s\S]*?<span>([\s\S]*?)</span>',
            block,
        )
        if not title_match:
            continue
        href = title_match.group(1).replace("&amp;", "&")
        company_match = re.search(r'class="corp_name"[\s\S]*?<a[^>]*>([\s\S]*?)</a>', block)
        condition_match = re.search(r'class="job_condition">([\s\S]*?)</div>', block)
        deadline_match = re.search(r'class="date">([\s\S]*?)</span>', block)
        spans: list[str] = []
        if condition_match:
            spans = [
                _strip_tags(match.group(1))
                for match in re.finditer(r"<span[^>]*>([\s\S]*?)</span>", condition_match.group(1))
            ]
        results.append(
            JobSearchResult(
                id=f"saramin-{index}",
                title=_strip_tags(title_match.group(2)),
                company=_strip_tags(company_match.group(1)) if company_match else "",
                location=spans[0] if len(spans) >= 1 else "-",
                source="사람인",
                url=href if href.startswith("http") else f"https://www.saramin.co.kr{href}",
                type=spans[3] if len(spans) >= 4 else "-",
                experience=spans[1] if len(spans) >= 2 else "-",
                salary="-",
                deadline=_strip_tags(deadline_match.group(1)) if deadline_match else "-",
                description="",
            )
        )
    return results


def _search_wanted(query: str) -> list[JobSearchResult]:
    url = "https://www.wanted.co.kr/api/v4/jobs"
    params = {"query": query, "country": "kr", "limit": 15, "offset": 0}
    response = httpx.get(url, params=params, headers=SEARCH_HEADERS, timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    results: list[JobSearchResult] = []
    for index, item in enumerate(payload.get("data") or []):
        address = item.get("address") or {}
        company = item.get("company") or {}
        results.append(
            JobSearchResult(
                id=f"wanted-{item.get('id') or index}",
                title=str(item.get("position") or ""),
                company=str(company.get("name") or ""),
                location=str(address.get("full_location") or address.get("location") or "-"),
                source="원티드",
                url=f"https://www.wanted.co.kr/wd/{item.get('id')}",
                type="-",
                experience=str(item.get("required_experience") or "-"),
                salary="-",
                deadline=str(item.get("due_time") or "-")[:10],
                description="",
            )
        )
    return results


def search_jobs(query: str) -> dict[str, Any]:
    korean_query, english_query, translated_query = _query_pair(query)
    all_results: list[JobSearchResult] = []
    provider_statuses: list[SearchProviderStatus] = []

    for key, label, provider_query, call in (
        ("saramin", "사람인", korean_query, lambda: _search_saramin(korean_query)),
        ("wanted", "원티드", korean_query, lambda: _search_wanted(korean_query)),
        ("efinancial", "eFinancial", english_query, lambda: _search_efinancial(english_query)),
    ):
        query_label = _provider_query_label(query, provider_query)
        try:
            batch = call()
            all_results.extend(batch)
            provider_statuses.append(
                SearchProviderStatus(
                    key=key,
                    label=label,
                    status="ok" if batch else "empty",
                    tone="ok" if batch else "warn",
                    count=len(batch),
                    state_label="정상" if batch else "결과 없음",
                    detail=f"{len(batch)}건 확인" if batch else "정상 응답, 결과 없음",
                    query=provider_query,
                    query_label=query_label,
                )
            )
        except Exception as exc:
            message = _provider_error_message(exc)
            provider_statuses.append(
                SearchProviderStatus(
                    key=key,
                    label=label,
                    status="error",
                    tone="error",
                    count=0,
                    state_label="오류",
                    detail=message,
                    query=provider_query,
                    query_label=query_label,
                    message=message,
                )
            )

    result_dicts = [asdict(result) for result in all_results]
    provider_summary = _provider_summary(provider_statuses)
    return {
        "results": result_dicts,
        "count": len(result_dicts),
        "translated_query": translated_query,
        "provider_statuses": [asdict(item) for item in provider_statuses],
        "provider_summary": provider_summary,
        "degraded": provider_summary["error"] > 0,
        "sources": {
            "전체": len(result_dicts),
            "사람인": sum(1 for item in result_dicts if item["source"] == "사람인"),
            "원티드": sum(1 for item in result_dicts if item["source"] == "원티드"),
            "eFinancial": sum(1 for item in result_dicts if item["source"] == "eFinancial"),
        },
    }
