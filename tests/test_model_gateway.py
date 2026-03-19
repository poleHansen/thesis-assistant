from __future__ import annotations

import unittest

from app.domain import ModelProviderSettings, ModelSettingsPayload
from app.model_gateway import ModelGateway
from app.providers import ProviderError, ProviderResponse


class FakeProvider:
    def __init__(self, provider_name: str, *, should_fail: bool = False) -> None:
        self.provider_name = provider_name
        self.should_fail = should_fail
        self.calls: list[str] = []

    def chat(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        self.calls.append(model)
        if self.should_fail:
            raise ProviderError(f"{self.provider_name} failed")
        return ProviderResponse(provider=self.provider_name, model=model, content=prompt)

    def embedding(self, text: str) -> list[float]:
        return [0.1]


class ModelGatewayTest(unittest.TestCase):
    def test_gateway_falls_back_to_stub_without_keys(self) -> None:
        gateway = ModelGateway()
        result = gateway.complete("writer", "璇风敓鎴愪竴涓憳瑕併€?")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.provider, "stub")
        self.assertIn("根据离线规则", result.content)

    def test_gateway_uses_task_route_model(self) -> None:
        settings = ModelSettingsPayload(
            providers=[
                ModelProviderSettings(
                    id="openai",
                    label="OpenAI",
                    api_base="https://example.com/v1",
                    api_key="sk-openai",
                    priority=1,
                    enabled=True,
                    models={"planner": "planner-model"},
                ),
                ModelProviderSettings(
                    id="kimi",
                    label="Kimi",
                    api_base="https://kimi.example/v1",
                    api_key="sk-kimi",
                    priority=2,
                    enabled=True,
                    models={"planner": "backup-model"},
                ),
            ],
            task_routes={"planner": "openai"},
        )
        gateway = ModelGateway(settings)
        primary = FakeProvider("openai")
        fallback = FakeProvider("kimi")
        gateway.providers = {"openai": primary, "kimi": fallback}

        result = gateway.complete("planner", "plan this")

        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "planner-model")
        self.assertFalse(result.fallback_used)
        self.assertEqual(primary.calls, ["planner-model"])
        self.assertEqual(fallback.calls, [])

    def test_gateway_falls_back_by_priority_when_primary_fails(self) -> None:
        settings = ModelSettingsPayload(
            providers=[
                ModelProviderSettings(
                    id="openai",
                    label="OpenAI",
                    api_base="https://example.com/v1",
                    api_key="sk-openai",
                    priority=1,
                    enabled=True,
                    models={"planner": "planner-model"},
                ),
                ModelProviderSettings(
                    id="deepseek",
                    label="DeepSeek",
                    api_base="https://deepseek.example/v1",
                    api_key="sk-deepseek",
                    priority=2,
                    enabled=True,
                    models={"planner": "deepseek-planner"},
                ),
                ModelProviderSettings(
                    id="kimi",
                    label="Kimi",
                    api_base="https://kimi.example/v1",
                    api_key="sk-kimi",
                    priority=3,
                    enabled=True,
                    models={"planner": "kimi-planner"},
                ),
            ],
            task_routes={"planner": "openai"},
        )
        gateway = ModelGateway(settings)
        primary = FakeProvider("openai", should_fail=True)
        secondary = FakeProvider("deepseek")
        tertiary = FakeProvider("kimi")
        gateway.providers = {
            "openai": primary,
            "deepseek": secondary,
            "kimi": tertiary,
        }

        result = gateway.complete("planner", "plan this")

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.model, "deepseek-planner")
        self.assertTrue(result.fallback_used)
        self.assertEqual(primary.calls, ["planner-model"])
        self.assertEqual(secondary.calls, ["deepseek-planner"])
        self.assertEqual(tertiary.calls, [])


if __name__ == "__main__":
    unittest.main()
