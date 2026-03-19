from __future__ import annotations

import importlib
import shutil
import unittest
import uuid
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - environment-dependent
    TestClient = None

from app.model_settings import ModelSettingsStore
from app.providers import ProviderResponse
from app.utils import to_plain_data


class FakeProvider:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
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
        return ProviderResponse(provider=self.provider_name, model=model, content=prompt)

    def embedding(self, text: str) -> list[float]:
        return [0.2]


@unittest.skipIf(TestClient is None, "fastapi is not installed in the current environment")
class ModelSettingsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.main = importlib.import_module("app.main")
        self.root = Path("tests_runtime") / f"model-settings-api-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.original_store = self.main.model_settings_store
        self.original_settings = self.main.gateway.get_settings()
        self.main.model_settings_store = ModelSettingsStore(self.root / "model_settings.json")
        self.main.gateway.reload(self.main.model_settings_store.load())
        self.client = TestClient(self.main.app)

    def tearDown(self) -> None:
        self.main.model_settings_store = self.original_store
        self.main.gateway.reload(self.original_settings)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_get_model_settings_returns_defaults(self) -> None:
        response = self.client.get("/settings/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_routes"]["planner"], "openai")
        self.assertEqual(payload["providers"][0]["id"], "openai")

    def test_put_model_settings_updates_gateway(self) -> None:
        payload = to_plain_data(self.main.model_settings_store.default_settings())
        payload["providers"][0]["api_key"] = "sk-test"
        payload["providers"][0]["models"]["planner"] = "gpt-test-planner"

        response = self.client.put("/settings/models", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.main.model_settings_store.path.exists())
        provider = FakeProvider("openai")
        self.main.gateway.providers["openai"] = provider

        result = self.main.gateway.complete("planner", "plan this")

        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "gpt-test-planner")
        self.assertEqual(provider.calls, ["gpt-test-planner"])

    def test_put_model_settings_rejects_invalid_payload(self) -> None:
        payload = to_plain_data(self.main.model_settings_store.default_settings())
        payload["task_routes"]["planner"] = "unknown"

        response = self.client.put("/settings/models", json=payload)

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
