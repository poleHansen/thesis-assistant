from __future__ import annotations

from dataclasses import dataclass

from app.domain import ModelRoutingPolicy, ProviderConfig
from app.providers import OpenAICompatibleProvider, ProviderError, ProviderResponse, StubProvider


@dataclass(slots=True)
class GatewayResult:
    provider: str
    model: str
    content: str
    fallback_used: bool


class ModelGateway:
    def __init__(
        self,
        provider_configs: dict[str, ProviderConfig] | None = None,
        routing_policies: dict[str, ModelRoutingPolicy] | None = None,
    ) -> None:
        self.provider_configs = provider_configs or self.default_provider_configs()
        self.routing_policies = routing_policies or self.default_routing_policies()
        self.providers = {
            name: OpenAICompatibleProvider(cfg.provider, cfg.api_base, cfg.api_key_env)
            for name, cfg in self.provider_configs.items()
        }
        self.stub_provider = StubProvider()

    @staticmethod
    def default_provider_configs() -> dict[str, ProviderConfig]:
        return {
            "openai": ProviderConfig(
                provider="openai",
                api_base="https://api.openai.com/v1",
                api_key_env="OPENAI_API_KEY",
                model_aliases={
                    "planner": "gpt-4o-mini",
                    "reviewer": "gpt-4o-mini",
                    "writer": "gpt-4o-mini",
                },
                priority=1,
            ),
            "deepseek": ProviderConfig(
                provider="deepseek",
                api_base="https://api.deepseek.com/v1",
                api_key_env="DEEPSEEK_API_KEY",
                model_aliases={
                    "code": "deepseek-chat",
                    "planner": "deepseek-chat",
                },
                priority=2,
            ),
            "kimi": ProviderConfig(
                provider="kimi",
                api_base="https://api.moonshot.cn/v1",
                api_key_env="MOONSHOT_API_KEY",
                model_aliases={
                    "writer": "moonshot-v1-128k",
                    "synthesizer": "moonshot-v1-128k",
                },
                priority=3,
            ),
        }

    @staticmethod
    def default_routing_policies() -> dict[str, ModelRoutingPolicy]:
        return {
            "planner": ModelRoutingPolicy(
                task_type="planner",
                primary_model="openai:planner",
                fallback_models=["kimi:synthesizer", "deepseek:planner"],
            ),
            "reviewer": ModelRoutingPolicy(
                task_type="reviewer",
                primary_model="openai:reviewer",
                fallback_models=["kimi:writer"],
            ),
            "consistency": ModelRoutingPolicy(
                task_type="consistency",
                primary_model="openai:reviewer",
                fallback_models=["deepseek:planner"],
            ),
            "survey_synthesizer": ModelRoutingPolicy(
                task_type="survey_synthesizer",
                primary_model="kimi:synthesizer",
                fallback_models=["openai:writer"],
            ),
            "writer": ModelRoutingPolicy(
                task_type="writer",
                primary_model="kimi:writer",
                fallback_models=["openai:writer"],
            ),
            "code": ModelRoutingPolicy(
                task_type="code",
                primary_model="deepseek:code",
                fallback_models=["openai:writer"],
            ),
        }

    def complete(
        self,
        task_type: str,
        prompt: str,
        *,
        system_prompt: str = "",
    ) -> GatewayResult:
        policy = self.routing_policies.get(task_type) or ModelRoutingPolicy(
            task_type=task_type,
            primary_model="openai:writer",
            fallback_models=["kimi:writer", "deepseek:planner"],
        )
        aliases = [policy.primary_model, *policy.fallback_models]
        last_error: Exception | None = None

        for idx, alias in enumerate(aliases):
            provider_name, model_key = alias.split(":", 1)
            provider_cfg = self.provider_configs[provider_name]
            provider = self.providers[provider_name]
            model_name = provider_cfg.model_aliases.get(model_key, model_key)
            try:
                response = provider.chat(
                    model=model_name,
                    prompt=prompt,
                    system_prompt=system_prompt or f"You are the {task_type} agent.",
                    temperature=policy.temperature,
                    max_tokens=policy.max_tokens,
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
            temperature=policy.temperature,
            max_tokens=policy.max_tokens,
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
