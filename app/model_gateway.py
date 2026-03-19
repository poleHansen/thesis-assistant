from __future__ import annotations

from dataclasses import dataclass

from app.domain import (
    MODEL_PROVIDER_TEST_TASK_ORDER,
    MODEL_TASK_TYPES,
    ModelProviderSettings,
    ModelProviderTestResult,
    ModelSettingsPayload,
)
from app.model_settings import ModelSettingsStore
from app.providers import OpenAICompatibleProvider, ProviderError, StubProvider


@dataclass(slots=True)
class GatewayResult:
    provider: str
    model: str
    content: str
    fallback_used: bool


class ModelGateway:
    def __init__(self, settings: ModelSettingsPayload | None = None) -> None:
        self.stub_provider = StubProvider()
        initial_settings = settings or ModelSettingsStore().load()
        self.reload(initial_settings)

    def reload(self, settings: ModelSettingsPayload) -> None:
        self.settings = settings
        self.provider_settings = {item.id: item for item in settings.providers}
        self.providers = {
            item.id: OpenAICompatibleProvider(item.id, item.api_base, item.api_key)
            for item in settings.providers
            if item.enabled
        }

    def get_settings(self) -> ModelSettingsPayload:
        return self.settings

    def test_provider(self, provider_settings: ModelProviderSettings) -> ModelProviderTestResult:
        model_name = self.pick_test_model(provider_settings)
        if not model_name:
            return ModelProviderTestResult(
                ok=False,
                provider=provider_settings.id,
                model="",
                message="No model is configured for provider testing.",
                response_preview=None,
            )

        provider = OpenAICompatibleProvider(
            provider_settings.id,
            provider_settings.api_base,
            provider_settings.api_key,
        )
        try:
            response = provider.chat(
                model=model_name,
                prompt="Reply with a short acknowledgement for this connectivity test.",
                system_prompt="You are a connectivity test assistant.",
                temperature=0.0,
                max_tokens=32,
            )
        except ProviderError as exc:
            return ModelProviderTestResult(
                ok=False,
                provider=provider_settings.id,
                model=model_name,
                message=str(exc),
                response_preview=None,
            )

        preview = response.content.strip().replace("\n", " ")[:200] or None
        return ModelProviderTestResult(
            ok=True,
            provider=response.provider,
            model=response.model,
            message="Provider test succeeded.",
            response_preview=preview,
        )

    def complete(
        self,
        task_type: str,
        prompt: str,
        *,
        system_prompt: str = "",
    ) -> GatewayResult:
        route_task = task_type if task_type in MODEL_TASK_TYPES else "writer"
        candidates = self._resolve_candidates(route_task)
        last_error: Exception | None = None

        for idx, provider_cfg in enumerate(candidates):
            provider = self.providers.get(provider_cfg.id)
            model_name = provider_cfg.models.get(route_task, "")
            if not provider or not model_name:
                continue
            try:
                response = provider.chat(
                    model=model_name,
                    prompt=prompt,
                    system_prompt=system_prompt or f"You are the {task_type} agent.",
                    temperature=0.2,
                    max_tokens=4096,
                )
                return GatewayResult(
                    provider=response.provider,
                    model=response.model,
                    content=response.content,
                    fallback_used=idx > 0,
                )
            except ProviderError as exc:
                last_error = exc

        fallback = self.stub_provider.chat(
            model=f"offline-{task_type}",
            prompt=prompt,
            system_prompt=system_prompt or f"You are the {task_type} agent.",
            temperature=0.2,
            max_tokens=4096,
        )
        if last_error:
            fallback.content += f"\n\n[provider_failover] {last_error}"
        return GatewayResult(
            provider=fallback.provider,
            model=fallback.model,
            content=fallback.content,
            fallback_used=True,
        )

    def embedding(self, provider_name: str, text: str) -> list[float]:
        provider = self.providers.get(provider_name) or self.stub_provider
        return provider.embedding(text)

    @staticmethod
    def pick_test_model(provider_settings: ModelProviderSettings) -> str:
        for task in MODEL_PROVIDER_TEST_TASK_ORDER:
            model_name = provider_settings.models.get(task, "").strip()
            if model_name:
                return model_name
        return ""

    def _resolve_candidates(self, task_type: str) -> list[ModelProviderSettings]:
        provider_configs = sorted(
            (
                item
                for item in self.settings.providers
                if item.enabled and item.models.get(task_type)
            ),
            key=lambda item: (item.priority, item.id),
        )
        if not provider_configs:
            return []

        primary_provider_id = self.settings.task_routes.get(task_type, "")
        primary = next(
            (item for item in provider_configs if item.id == primary_provider_id),
            None,
        )
        if not primary:
            return provider_configs

        fallbacks = [item for item in provider_configs if item.id != primary.id]
        return [primary, *fallbacks]
