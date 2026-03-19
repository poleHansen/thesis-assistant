from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from app.model_settings import ModelSettingsError, ModelSettingsStore
from app.utils import to_plain_data


class ModelSettingsStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("tests_runtime") / f"model-settings-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = ModelSettingsStore(self.root / "model_settings.json")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_load_returns_defaults_when_file_missing(self) -> None:
        settings = self.store.load()

        self.assertEqual(settings.task_routes["planner"], "openai")
        self.assertEqual(settings.providers[0].id, "openai")

    def test_save_and_reload_round_trip(self) -> None:
        payload = to_plain_data(self.store.default_settings())
        payload["providers"][0]["api_key"] = "sk-test"
        payload["providers"][0]["models"]["planner"] = "gpt-test-planner"

        saved = self.store.save(payload)
        reloaded = self.store.load()

        self.assertEqual(saved.providers[0].api_key, "sk-test")
        self.assertEqual(reloaded.providers[0].models["planner"], "gpt-test-planner")

    def test_validate_rejects_duplicate_provider_ids(self) -> None:
        payload = to_plain_data(self.store.default_settings())
        payload["providers"][1]["id"] = "openai"

        with self.assertRaises(ModelSettingsError):
            self.store.save(payload)

    def test_validate_rejects_invalid_task_route(self) -> None:
        payload = to_plain_data(self.store.default_settings())
        payload["task_routes"]["planner"] = "missing-provider"

        with self.assertRaises(ModelSettingsError):
            self.store.save(payload)

    def test_validate_rejects_missing_task_model(self) -> None:
        payload = to_plain_data(self.store.default_settings())
        payload["providers"][0]["models"]["planner"] = ""

        with self.assertRaises(ModelSettingsError):
            self.store.save(payload)


if __name__ == "__main__":
    unittest.main()
