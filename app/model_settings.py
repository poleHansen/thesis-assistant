from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from app.config import SETTINGS
from app.domain import MODEL_TASK_TYPES, ModelProviderSettings, ModelSettingsPayload
from app.utils import dumps_json


class ModelSettingsError(ValueError):
    pass


class ModelSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        SETTINGS.ensure_directories()
        self.path = path or SETTINGS.model_settings_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def default_settings() -> ModelSettingsPayload:
        return ModelSettingsPayload(
            providers=[
                ModelProviderSettings(
                    id="openai",
                    label="OpenAI",
                    api_base="https://api.openai.com/v1",
                    api_key="",
                    priority=1,
                    enabled=True,
                    models={
                        "planner": "gpt-4o-mini",
                        "reviewer": "gpt-4o-mini",
                        "consistency": "gpt-4o-mini",
                        "writer": "gpt-4o-mini",
                    },
                ),
                ModelProviderSettings(
                    id="deepseek",
                    label="DeepSeek",
                    api_base="https://api.deepseek.com/v1",
                    api_key="",
                    priority=2,
                    enabled=True,
                    models={
                        "planner": "deepseek-chat",
                        "code": "deepseek-chat",
                    },
                ),
                ModelProviderSettings(
                    id="kimi",
                    label="Kimi",
                    api_base="https://api.moonshot.cn/v1",
                    api_key="",
                    priority=3,
                    enabled=True,
                    models={
                        "survey_synthesizer": "moonshot-v1-128k",
                        "writer": "moonshot-v1-128k",
                    },
                ),
            ],
            task_routes={
                "planner": "openai",
                "reviewer": "openai",
                "consistency": "openai",
                "survey_synthesizer": "kimi",
                "writer": "kimi",
                "code": "deepseek",
            },
        )

    def load(self) -> ModelSettingsPayload:
        if not self.path.exists():
            return self.default_settings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return self.validate(payload)

    def save(self, payload: ModelSettingsPayload | dict[str, Any]) -> ModelSettingsPayload:
        settings = self.validate(payload)
        self.path.write_text(dumps_json(settings), encoding="utf-8")
        return settings

    def validate(self, payload: ModelSettingsPayload | dict[str, Any]) -> ModelSettingsPayload:
        data = self._to_dict(payload)
        providers_raw = data.get("providers")
        if not isinstance(providers_raw, list) or not providers_raw:
            raise ModelSettingsError("providers must be a non-empty list")

        normalized_providers: list[ModelProviderSettings] = []
        seen_ids: set[str] = set()
        for item in providers_raw:
            provider = self.normalize_provider(item)
            if provider.id in seen_ids:
                raise ModelSettingsError(f"provider id '{provider.id}' must be unique")
            seen_ids.add(provider.id)
            normalized_providers.append(provider)

        normalized_providers.sort(key=lambda item: (item.priority, item.id))
        provider_map = {item.id: item for item in normalized_providers}
        enabled_ids = {item.id for item in normalized_providers if item.enabled}

        task_routes_raw = data.get("task_routes")
        if not isinstance(task_routes_raw, dict):
            raise ModelSettingsError("task_routes must be an object")

        normalized_routes: dict[str, str] = {}
        for task in MODEL_TASK_TYPES:
            provider_id = task_routes_raw.get(task)
            if not isinstance(provider_id, str) or not provider_id.strip():
                raise ModelSettingsError(f"task route '{task}' is required")
            provider_key = provider_id.strip()
            if provider_key not in provider_map:
                raise ModelSettingsError(f"task route '{task}' points to unknown provider '{provider_key}'")
            if provider_key not in enabled_ids:
                raise ModelSettingsError(f"task route '{task}' points to disabled provider '{provider_key}'")
            if not provider_map[provider_key].models.get(task):
                raise ModelSettingsError(
                    f"provider '{provider_key}' must define a model for task '{task}'"
                )
            normalized_routes[task] = provider_key

        return ModelSettingsPayload(
            providers=normalized_providers,
            task_routes=normalized_routes,
        )

    def normalize_provider(self, item: Any) -> ModelProviderSettings:
        if is_dataclass(item):
            raw = asdict(item)
        elif isinstance(item, dict):
            raw = item
        else:
            raise ModelSettingsError("provider entries must be objects")

        provider_id = str(raw.get("id", "")).strip()
        if not provider_id:
            raise ModelSettingsError("provider id is required")

        label = str(raw.get("label", "")).strip() or provider_id
        api_base = str(raw.get("api_base", "")).strip().rstrip("/")
        if not api_base:
            raise ModelSettingsError(f"provider '{provider_id}' api_base is required")

        api_key = str(raw.get("api_key", "")).strip()
        try:
            priority = int(raw.get("priority", 10))
        except (TypeError, ValueError) as exc:
            raise ModelSettingsError(f"provider '{provider_id}' priority must be an integer") from exc

        # Optional API mode: controls which OpenAI-compatible endpoint is used.
        # Defaults to chat_completions for backward compatibility.
        api_mode_raw = str(raw.get("api_mode", "chat_completions") or "chat_completions").strip().lower()
        if api_mode_raw in {"chat", "chat_completion", "chat-completions", "chat_completions"}:
            api_mode = "chat_completions"
        elif api_mode_raw in {"responses", "response"}:
            api_mode = "responses"
        else:
            raise ModelSettingsError(
                f"provider '{provider_id}' api_mode must be one of 'chat_completions' or 'responses'"
            )

        models_raw = raw.get("models", {})
        if not isinstance(models_raw, dict):
            raise ModelSettingsError(f"provider '{provider_id}' models must be an object")

        normalized_models: dict[str, str] = {}
        for task in MODEL_TASK_TYPES:
            value = models_raw.get(task, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ModelSettingsError(
                    f"provider '{provider_id}' model for task '{task}' must be a string"
                )
            model_name = value.strip()
            if model_name:
                normalized_models[task] = model_name

        return ModelProviderSettings(
            id=provider_id,
            label=label,
            api_base=api_base,
            api_key=api_key,
            priority=priority,
            enabled=bool(raw.get("enabled", True)),
             api_mode=api_mode,
            models=normalized_models,
        )

    @staticmethod
    def _to_dict(payload: ModelSettingsPayload | dict[str, Any]) -> dict[str, Any]:
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, dict):
            return payload
        raise ModelSettingsError("settings payload must be an object")
