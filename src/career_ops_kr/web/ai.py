from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from career_ops_kr.web.db import connection_scope


OPENAI_MODEL = "gpt-5.4-mini"
GEMINI_MODEL = "gemini-2.5-flash"
ALLOWED_SETTING_KEYS = {
    "AI_PROVIDER",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
}


class AiServiceError(RuntimeError):
    pass


@dataclass(slots=True)
class AiProviderConfig:
    provider: str
    api_key: str
    source: str


def ai_feature_enabled() -> bool:
    return os.getenv("CAREER_OPS_WEB_ENABLE_AI", "").strip().lower() in {"1", "true", "yes", "on"}


def load_settings(db_path: Path | None = None) -> dict[str, str]:
    with connection_scope(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def get_setting(key: str, db_path: Path | None = None) -> str | None:
    if key not in ALLOWED_SETTING_KEYS:
        raise ValueError(f"Unsupported setting key: {key}")
    settings = load_settings(db_path)
    return settings.get(key) or os.getenv(key)


def store_setting(key: str, value: str | None, db_path: Path | None = None) -> None:
    if key not in ALLOWED_SETTING_KEYS:
        raise ValueError(f"Unsupported setting key: {key}")
    with connection_scope(db_path) as conn:
        if value:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()


def resolve_provider(db_path: Path | None = None) -> AiProviderConfig:
    if not ai_feature_enabled():
        raise AiServiceError("AI 기능이 현재 비활성화되어 있습니다.")

    settings = load_settings(db_path)
    preferred = settings.get("AI_PROVIDER", "").strip().lower()
    gemini_key = settings.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    openai_key = settings.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

    if preferred == "openai" and openai_key:
        return AiProviderConfig(provider="openai", api_key=openai_key, source="settings")
    if preferred == "gemini" and gemini_key:
        return AiProviderConfig(provider="gemini", api_key=gemini_key, source="settings")
    if gemini_key:
        return AiProviderConfig(provider="gemini", api_key=gemini_key, source="auto")
    if openai_key:
        return AiProviderConfig(provider="openai", api_key=openai_key, source="auto")
    raise AiServiceError("GEMINI_API_KEY 또는 OPENAI_API_KEY를 설정 페이지에서 입력해주세요.")


def _extract_openai_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise AiServiceError("OpenAI returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "".join(texts).strip()
    raise AiServiceError("OpenAI response did not contain text content.")


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise AiServiceError("Gemini returned no candidates.")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise AiServiceError("Gemini response did not contain text content.")
    return text


def generate_text(prompt: str, *, db_path: Path | None = None) -> str:
    provider = resolve_provider(db_path)
    with httpx.Client(timeout=60.0) as client:
        if provider.provider == "openai":
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {provider.api_key}"},
                json={
                    "model": OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            return _extract_openai_text(response.json())

        response = client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": provider.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        response.raise_for_status()
        return _extract_gemini_text(response.json())


def generate_json(prompt: str, *, db_path: Path | None = None) -> dict[str, Any]:
    provider = resolve_provider(db_path)
    json_prompt = f"{prompt}\n\nReturn ONLY valid JSON. Do not wrap it in markdown."
    with httpx.Client(timeout=60.0) as client:
        if provider.provider == "openai":
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {provider.api_key}"},
                json={
                    "model": OPENAI_MODEL,
                    "messages": [{"role": "user", "content": json_prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            raw = _extract_openai_text(response.json())
        else:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                params={"key": provider.api_key},
                json={
                    "contents": [{"parts": [{"text": json_prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )
            response.raise_for_status()
            raw = _extract_gemini_text(response.json())

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AiServiceError(f"Model did not return valid JSON: {exc}") from exc


def translate_query(text: str, *, target_language: str, db_path: Path | None = None) -> str:
    prompt = (
        "Translate this job-search keyword into a single natural search query.\n"
        f"Target language: {target_language}\n"
        "Return exactly one query with no alternatives or commentary.\n\n"
        f"Keyword: {text}"
    )
    try:
        translated = generate_text(prompt, db_path=db_path)
    except AiServiceError:
        return text
    first_line = translated.strip().splitlines()[0]
    cleaned = first_line.split(",")[0].replace('"', "").replace("'", "").strip()
    return cleaned or text
