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

    def test_post_project_repair_returns_remediation_summary(self) -> None:
        original_repair = self.main.supervisor.repair

        def fake_repair(state):
            state.result_schema["remediation_summary"] = {
                "applied": True,
                "applied_keys": ["citation_binding"],
                "actions": [{"key": "citation_binding", "status": "applied", "message": "Auto remediation applied."}],
                "rerun_phases": ["review"],
            }
            state.workflow_outcome = "rollback_success"
            return state

        self.main.supervisor.repair = fake_repair
        try:
            response = self.client.post("/projects/project-workflow-api/repair")
        finally:
            self.main.supervisor.repair = original_repair

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["workflow_outcome"], "rollback_success")
        self.assertTrue(payload["remediation_summary"]["applied"])

    def test_download_artifact_returns_attachment_headers_for_docx(self) -> None:
        artifact_path = self.root / "thesis.docx"
        artifact_path.write_bytes(b"fake-docx-content")

        state = self.main.repository.get("project-workflow-api")
        assert state is not None
        state.artifacts.thesis_docx = str(artifact_path)
        self.main.repository.save(state)

        response = self.client.get("/projects/project-workflow-api/artifacts/thesis_docx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn('filename="thesis.docx"', response.headers["content-disposition"])

    def test_download_artifact_rejects_legacy_markdown_thesis(self) -> None:
        artifact_path = self.root / "thesis.md"
        artifact_path.write_text("legacy thesis markdown", encoding="utf-8")

        state = self.main.repository.get("project-workflow-api")
        assert state is not None
        state.artifacts.thesis_docx = str(artifact_path)
        self.main.repository.save(state)

        response = self.client.get("/projects/project-workflow-api/artifacts/thesis_docx")

        self.assertEqual(response.status_code, 409)
        self.assertIn("Legacy thesis artifact is markdown", response.text)