from __future__ import annotations

from datetime import date
from typing import Any

from career_ops_kr.web.common import parse_tracker_date, safe_int, safe_text


FOLLOW_UP_SCHEDULING_STATUSES = {"검토중", "지원예정"}


def build_follow_up_agenda(
    rows: list[dict[str, Any]],
    *,
    horizon_days: int = 7,
    today: date | None = None,
) -> dict[str, Any]:
    current_day = today or date.today()
    normalized_horizon = max(1, horizon_days)
    sections = {
        "overdue": _agenda_section(
            key="overdue",
            label="늦은 팔로업",
            tone="error",
            description="이미 날짜가 지난 항목입니다. 먼저 상태와 메모를 갱신하세요.",
        ),
        "today": _agenda_section(
            key="today",
            label="오늘 할 일",
            tone="warn",
            description="오늘 처리할 follow-up입니다.",
        ),
        "upcoming": _agenda_section(
            key="upcoming",
            label=f"앞으로 {normalized_horizon}일",
            tone="ok",
            description=f"오늘 이후 {normalized_horizon}일 안에 다시 볼 항목입니다.",
        ),
        "unscheduled_active": _agenda_section(
            key="unscheduled_active",
            label="날짜 미설정 active",
            tone="warn",
            description="검토중 또는 지원예정인데 follow-up 날짜가 없는 항목입니다.",
        ),
        "later": _agenda_section(
            key="later",
            label="그 이후 일정",
            tone="ok",
            description=f"{normalized_horizon}일 이후 예정된 follow-up입니다.",
        ),
    }

    for row in rows:
        item = _follow_up_item(row, today=current_day)
        if item["follow_up"] is None:
            if item["status"] in FOLLOW_UP_SCHEDULING_STATUSES:
                sections["unscheduled_active"]["items"].append(item)
            continue

        days_until = item["days_until"]
        if days_until is None:
            continue
        if days_until < 0:
            sections["overdue"]["items"].append(item)
        elif days_until == 0:
            sections["today"]["items"].append(item)
        elif days_until <= normalized_horizon:
            sections["upcoming"]["items"].append(item)
        else:
            sections["later"]["items"].append(item)

    sections["overdue"]["items"].sort(key=lambda item: (item["follow_up"] or "", item["company"], item["position"]))
    sections["today"]["items"].sort(key=lambda item: (item["company"], item["position"]))
    sections["upcoming"]["items"].sort(key=lambda item: (item["follow_up"] or "", item["company"], item["position"]))
    sections["later"]["items"].sort(key=lambda item: (item["follow_up"] or "", item["company"], item["position"]))
    sections["unscheduled_active"]["items"].sort(
        key=lambda item: (item["status"], item["company"], item["position"], item["updated_at"] or ""),
    )

    ordered_sections = [
        sections["overdue"],
        sections["today"],
        sections["upcoming"],
        sections["unscheduled_active"],
        sections["later"],
    ]
    counts = {section["key"]: len(section["items"]) for section in ordered_sections}
    preview_items = (
        sections["overdue"]["items"] + sections["today"]["items"] + sections["upcoming"]["items"] + sections["unscheduled_active"]["items"]
    )[:5]
    return {
        "today": current_day.isoformat(),
        "horizon_days": normalized_horizon,
        "counts": counts,
        "high_priority_count": sum(
            counts[key] for key in ("overdue", "today", "upcoming", "unscheduled_active")
        ),
        "sections": ordered_sections,
        "preview_items": preview_items,
    }


def _agenda_section(*, key: str, label: str, tone: str, description: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "tone": tone,
        "description": description,
        "items": [],
    }


def _follow_up_item(row: dict[str, Any], *, today: date) -> dict[str, Any]:
    follow_up = parse_tracker_date(safe_text(row.get("follow_up")))
    days_until = (follow_up - today).days if follow_up else None
    return {
        "id": safe_int(row.get("id")),
        "company": safe_text(row.get("company")),
        "position": safe_text(row.get("position")),
        "status": safe_text(row.get("status")),
        "source": safe_text(row.get("source")),
        "follow_up": follow_up.isoformat() if follow_up else None,
        "follow_up_label": _follow_up_label(days_until),
        "days_until": days_until,
        "updated_at": safe_text(row.get("updated_at")),
        "detail_url": f"/tracker/{safe_int(row.get('id'))}" if safe_int(row.get("id")) is not None else None,
        "notes": safe_text(row.get("notes")),
    }


def _follow_up_label(days_until: int | None) -> str:
    if days_until is None:
        return "미설정"
    if days_until == 0:
        return "오늘"
    if days_until > 0:
        return f"D-{days_until}"
    return f"{abs(days_until)}일 지남"
