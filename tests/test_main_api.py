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

from app.domain import ProjectCreate, ProjectState
from app.repository import ProjectRepository


@unittest.skipIf(TestClient is None, "fastapi is not installed in the current environment")
class MainApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.main = importlib.import_module("app.main")
        self.root = Path("tests_runtime") / f"main-api-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.original_repository = self.main.repository
        self.main.repository = ProjectRepository(self.root / "test.db")
        self.client = TestClient(self.main.app)

        state = ProjectState(
            project_id="project-workflow-api",
            request=ProjectCreate(topic="中文文本分类算法"),
            workflow_phase="review",
            workflow_outcome="partial_success",
            current_node="consistency_checker",
            last_error="",
            last_failure_category="consistency",
        )
        state.result_schema["consistency_summary"] = {
            "findings": [
                {
                    "key": "citation_binding",
                    "label": "引用绑定 ↔ 文献记录",
                    "aligned": False,
                    "detail": "检查引用是否绑定到文献记录。",
                    "severity": "error",
                    "blocking": True,
                    "source": "literature_records",
                    "target": "paper_sections.参考文献",
                    "message": "论文中尚未形成可追溯的引用绑定。",
                    "recommendation": "论文中尚未形成可追溯的引用绑定。",
                }
            ]
        }
        self.main.repository.create(state)

    def tearDown(self) -> None:
        self.main.repository = self.original_repository
        shutil.rmtree(self.root, ignore_errors=True)

    def test_get_project_workflow_returns_structured_summary(self) -> None:
        response = self.client.get("/projects/project-workflow-api/workflow")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["workflow_phase"], "review")
        self.assertEqual(payload["workflow_outcome"], "partial_success")
        self.assertEqual(len(payload["blocking_findings"]), 1)