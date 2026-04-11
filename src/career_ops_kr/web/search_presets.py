from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable


SEARCH_PRESETS_SETTINGS_KEY = "SEARCH_PRESETS_V1"
SEARCH_PRESETS_LIMIT = 12
SEARCH_PRESETS_VERSION = 2


def list_search_presets(*, connection_scope: Callable[..., Any]) -> list[dict[str, Any]]:
    payload = _read_search_presets_payload(connection_scope=connection_scope)
    default_key = _normalize_preset_key(payload.get("default_preset_key"))
    presets = payload.get("presets") or []
    return _normalize_search_presets(presets, default_key=default_key)


def get_search_preset(preset_key: str, *, connection_scope: Callable[..., Any]) -> dict[str, Any] | None:
    normalized_key = _normalize_preset_key(preset_key)
    if not normalized_key:
        return None
    for preset in list_search_presets(connection_scope=connection_scope):
        if preset["key"] == normalized_key:
            return preset
    return None


def use_search_preset(preset_key: str, *, connection_scope: Callable[..., Any]) -> dict[str, Any] | None:
    normalized_key = _normalize_preset_key(preset_key)
    if not normalized_key:
        return None
    payload = _read_search_presets_payload(connection_scope=connection_scope)
    presets = payload.get("presets") or []
    target = next((preset for preset in presets if _normalize_preset_key(preset.get("key")) == normalized_key), None)
    if target is None or not _is_valid_search_preset(target):
        return None
    target["last_used_at"] = _timestamp_now()
    _save_search_presets_payload(
        {
            "version": SEARCH_PRESETS_VERSION,
            "default_preset_key": payload.get("default_preset_key"),
            "presets": presets,
        },
        connection_scope=connection_scope,
    )
    return get_search_preset(normalized_key, connection_scope=connection_scope)


def save_search_preset(
    name: str | None,
    query: str | None,
    *,
    connection_scope: Callable[..., Any],
    slugify: Callable[..., str],
    make_default: bool = False,
) -> dict[str, Any]:
    normalized_query = " ".join(str(query or "").split()).strip()
    if not normalized_query:
        raise ValueError("검색어가 비어 있습니다.")
    normalized_name = " ".join(str(name or "").split()).strip() or normalized_query[:40]

    payload = _read_search_presets_payload(connection_scope=connection_scope)
    presets = payload.get("presets") or []
    default_key = _normalize_preset_key(payload.get("default_preset_key"))
    timestamp = _timestamp_now()

    existing = next((preset for preset in presets if str(preset.get("query") or "").casefold() == normalized_query.casefold()), None)
    if existing:
        existing["name"] = normalized_name
        existing["query"] = normalized_query
        existing["updated_at"] = timestamp
        saved_key = _normalize_preset_key(existing.get("key"))
    else:
        key_base = slugify(normalized_name, fallback="search-preset")
        saved_key = f"{key_base}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        presets.append(
            {
                "key": saved_key,
                "name": normalized_name,
                "query": normalized_query,
                "created_at": timestamp,
                "updated_at": timestamp,
                "last_used_at": None,
            }
        )

    if make_default or (not default_key and saved_key):
        default_key = saved_key

    _save_search_presets_payload(
        {
            "version": SEARCH_PRESETS_VERSION,
            "default_preset_key": default_key,
            "presets": presets,
        },
        connection_scope=connection_scope,
    )
    saved = get_search_preset(saved_key, connection_scope=connection_scope)
    if saved is None:
        raise ValueError("검색 preset 저장에 실패했습니다.")
    return saved


def set_default_search_preset(preset_key: str, *, connection_scope: Callable[..., Any]) -> dict[str, Any]:
    normalized_key = _normalize_preset_key(preset_key)
    if not normalized_key:
        raise ValueError("Preset key required")
    payload = _read_search_presets_payload(connection_scope=connection_scope)
    presets = payload.get("presets") or []
    target = next((preset for preset in presets if _normalize_preset_key(preset.get("key")) == normalized_key), None)
    if target is None or not _is_valid_search_preset(target):
        raise ValueError("Preset not found")
    _save_search_presets_payload(
        {
            "version": SEARCH_PRESETS_VERSION,
            "default_preset_key": normalized_key,
            "presets": presets,
        },
        connection_scope=connection_scope,
    )
    saved = get_search_preset(normalized_key, connection_scope=connection_scope)
    if saved is None:
        raise ValueError("Preset not found")
    return saved


def delete_search_preset(preset_key: str, *, connection_scope: Callable[..., Any]) -> bool:
    normalized_key = _normalize_preset_key(preset_key)
    if not normalized_key:
        return False
    payload = _read_search_presets_payload(connection_scope=connection_scope)
    presets = payload.get("presets") or []
    next_presets = [preset for preset in presets if _normalize_preset_key(preset.get("key")) != normalized_key]
    if len(next_presets) == len(presets):
        return False
    default_key = _normalize_preset_key(payload.get("default_preset_key"))
    if default_key == normalized_key:
        default_key = _normalize_preset_key(next_presets[0].get("key")) if next_presets else None
    _save_search_presets_payload(
        {
            "version": SEARCH_PRESETS_VERSION,
            "default_preset_key": default_key,
            "presets": next_presets,
        },
        connection_scope=connection_scope,
    )
    return True


def _normalize_search_presets(presets: list[Any], *, default_key: str | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for value in presets:
        if not _is_valid_search_preset(value):
            continue
        normalized_key = _normalize_preset_key(value.get("key"))
        if not normalized_key:
            continue
        created_at = _normalize_optional_timestamp(value.get("created_at"))
        updated_at = _normalize_optional_timestamp(value.get("updated_at"))
        last_used_at = _normalize_optional_timestamp(value.get("last_used_at"))
        normalized.append(
            {
                "key": normalized_key,
                "name": str(value.get("name") or "").strip(),
                "query": str(value.get("query") or "").strip(),
                "created_at": created_at,
                "updated_at": updated_at,
                "last_used_at": last_used_at,
                "is_default": normalized_key == default_key,
                "activity_label": _activity_label(last_used_at=last_used_at, updated_at=updated_at, created_at=created_at),
            }
        )
    normalized.sort(
        key=lambda item: (
            1 if item["is_default"] else 0,
            item.get("last_used_at") or "",
            item.get("updated_at") or item.get("created_at") or "",
        ),
        reverse=True,
    )
    return normalized[:SEARCH_PRESETS_LIMIT]


def _read_search_presets_payload(*, connection_scope: Callable[..., Any]) -> dict[str, Any]:
    with connection_scope() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (SEARCH_PRESETS_SETTINGS_KEY,)).fetchone()
    return _load_search_presets_payload(row["value"] if row else None)


def _load_search_presets_payload(raw_value: Any) -> dict[str, Any]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return {"version": SEARCH_PRESETS_VERSION, "default_preset_key": None, "presets": []}
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {"version": SEARCH_PRESETS_VERSION, "default_preset_key": None, "presets": []}
    if not isinstance(payload, dict):
        return {"version": SEARCH_PRESETS_VERSION, "default_preset_key": None, "presets": []}
    version = payload.get("version")
    presets = payload.get("presets")
    if not isinstance(presets, list):
        return {"version": SEARCH_PRESETS_VERSION, "default_preset_key": None, "presets": []}
    if version == 1:
        return {
            "version": SEARCH_PRESETS_VERSION,
            "default_preset_key": None,
            "presets": [preset for preset in presets if _is_valid_search_preset(preset)],
        }
    if version != SEARCH_PRESETS_VERSION:
        return {"version": SEARCH_PRESETS_VERSION, "default_preset_key": None, "presets": []}
    return {
        "version": SEARCH_PRESETS_VERSION,
        "default_preset_key": _normalize_preset_key(payload.get("default_preset_key")),
        "presets": [preset for preset in presets if _is_valid_search_preset(preset)],
    }


def _is_valid_search_preset(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("key"), str)
        and bool(str(value.get("key") or "").strip())
        and isinstance(value.get("name"), str)
        and bool(str(value.get("name") or "").strip())
        and isinstance(value.get("query"), str)
        and bool(str(value.get("query") or "").strip())
    )


def _save_search_presets_payload(payload: dict[str, Any], *, connection_scope: Callable[..., Any]) -> None:
    presets = _normalize_search_presets(payload.get("presets") or [], default_key=_normalize_preset_key(payload.get("default_preset_key")))
    serializable = {
        "version": SEARCH_PRESETS_VERSION,
        "default_preset_key": next((preset["key"] for preset in presets if preset.get("is_default")), None),
        "presets": [
            {
                "key": preset["key"],
                "name": preset["name"],
                "query": preset["query"],
                "created_at": preset.get("created_at"),
                "updated_at": preset.get("updated_at"),
                "last_used_at": preset.get("last_used_at"),
            }
            for preset in presets[:SEARCH_PRESETS_LIMIT]
        ],
    }
    serialized = json.dumps(serializable, ensure_ascii=False, indent=2)
    with connection_scope() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SEARCH_PRESETS_SETTINGS_KEY, serialized),
        )
        conn.commit()


def _normalize_preset_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _timestamp_now() -> str:
    return datetime.now(UTC).isoformat()


def _activity_label(*, last_used_at: str | None, updated_at: str | None, created_at: str | None) -> str:
    if last_used_at:
        return f"마지막 사용 {_format_timestamp(last_used_at)}"
    if updated_at:
        return f"최근 수정 {_format_timestamp(updated_at)}"
    if created_at:
        return f"생성 {_format_timestamp(created_at)}"
    return "저장됨"


def _format_timestamp(value: str) -> str:
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
