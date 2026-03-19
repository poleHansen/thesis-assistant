from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(slots=True)
class AppSettings:
    app_name: str = "thesis-assistant"
    data_dir: Path = field(
        default_factory=lambda: Path(_env("THESIS_ASSISTANT_DATA_DIR", "workspace"))
    )
    db_path: Path = field(
        default_factory=lambda: Path(
            _env("THESIS_ASSISTANT_DB_PATH", "workspace/thesis_assistant.db")
        )
    )
    model_settings_path: Path = field(
        default_factory=lambda: Path(
            _env("THESIS_ASSISTANT_MODEL_SETTINGS_PATH", "workspace/model_settings.json")
        )
    )
    host: str = field(default_factory=lambda: _env("THESIS_ASSISTANT_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("THESIS_ASSISTANT_PORT", "8000")))

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_settings_path.parent.mkdir(parents=True, exist_ok=True)


SETTINGS = AppSettings()
