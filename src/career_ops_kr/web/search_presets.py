from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable


SEARCH_PRESETS_SETTINGS_KEY = "SEARCH_PRESETS_V1"
SEARCH_PRESETS_LIMIT = 12


def list_search_presets(*, connection_scope: Callable[..., Any]) -> list[dict[str, str]]:
    with connection_scope() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (SEARCH_PRESETS_SETTINGS_KEY,)).fetchone()
    payload = _load_search_presets_payload(row["value"] if row else None)
    presets = payload.get("presets") or []
    return [preset for preset in presets if _is_valid_search_preset(preset)]


def get_search_preset(preset_key: str, *, connection_scope: Callable[..., Any]) -> dict[str, str] | None:
    normalized_key = str(preset_key or "").strip()
    if not normalized_key:
        return None
    for preset in list_search_presets(connection_scope=connection_scope):
        if preset["key"] == normalized_key:
            return preset
    return None


def save_search_preset(
    name: str | None,
    query: str | None,
    *,
    connection_scope: Callable[..., Any],
    slugify: Callable[..., str],
) -> dict[str, str]:
    normalized_query = " ".join(str(query or "").split()).strip()
    if not normalized_query:
        raise ValueError("검색어가 비어 있습니다.")
    normalized_name = " ".join(str(name or "").split()).strip() or normalized_query[:40]
    presets = list_search_presets(connection_scope=connection_scope)
    timestamp = datetime.now(UTC).isoformat()

    existing = next((preset for preset in presets if preset["query"].casefold() == normalized_query.casefold()), None)
    if existing:
        existing["name"] = normalized_name
        existing["query"] = normalized_query
        existing["updated_at"] = timestamp
        saved = existing
    else:
        key_base = slugify(normalized_name, fallback="search-preset")
        saved = {
            "key": f"{key_base}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "name": normalized_name,
            "query": normalized_query,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        presets.insert(0, saved)

    presets.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    payload = {"version": 1, "presets": presets[:SEARCH_PRESETS_LIMIT]}
    _save_search_presets_payload(payload, connection_scope=connection_scope)
    return saved


def delete_search_preset(preset_key: str, *, connection_scope: Callable[..., Any]) -> bool:
    normalized_key = str(preset_key or "").strip()
    if not normalized_key:
        return False
    presets = list_search_presets(connection_scope=connection_scope)
    next_presets = [preset for preset in presets if preset["key"] != normalized_key]
    if len(next_presets) == len(presets):
        return False
    _save_search_presets_payload({"version": 1, "presets": next_presets}, connection_scope=connection_scope)
    return True


def _load_search_presets_payload(raw_value: Any) -> dict[str, Any]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return {"version": 1, "presets": []}
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {"version": 1, "presets": []}
    if not isinstance(payload, dict):
        return {"version": 1, "presets": []}
    if payload.get("version") != 1:
        return {"version": 1, "presets": []}
    presets = payload.get("presets")
    if not isinstance(presets, list):
        return {"version": 1, "presets": []}
    return {"version": 1, "presets": [preset for preset in presets if _is_valid_search_preset(preset)]}


def _is_valid_search_preset(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("key"), str)
        and bool(value["key"].strip())
        and isinstance(value.get("name"), str)
        and bool(value["name"].strip())
        and isinstance(value.get("query"), str)
        and bool(value["query"].strip())
    )


def _save_search_presets_payload(payload: dict[str, Any], *, connection_scope: Callable[..., Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    with connection_scope() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SEARCH_PRESETS_SETTINGS_KEY, serialized),
        )
        conn.commit()
