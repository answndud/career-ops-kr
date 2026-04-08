from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

def slugify(value: str, *, fallback: str = "item", limit: int = 80) -> str:
    normalized = value.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", normalized)
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:limit] or fallback


def load_yaml(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def parse_front_matter(path: str | Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_text(encoding="utf-8")
    if raw.startswith("---\n"):
        parts = raw.split("---\n", 2)
        if len(parts) >= 3:
            metadata = yaml.safe_load(parts[1]) or {}
            return metadata, parts[2].strip()
    return {}, raw.strip()


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def title_case(value: str | None) -> str:
    if not value:
        return "Unknown"
    return re.sub(r"\s+", " ", value).strip()
