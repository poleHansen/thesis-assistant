from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "project"


def to_plain_data(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain_data(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_plain_data(val) for key, val in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(to_plain_data(value), ensure_ascii=False, indent=2)


def loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)

