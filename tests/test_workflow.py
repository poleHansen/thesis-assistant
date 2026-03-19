from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import uuid

from app.domain import ProjectCreate, ProjectState
from app.model_gateway import ModelGateway
from app.repository import ProjectRepository
from app.storage import ProjectStorage
from app.template_service import TemplateService
from app.workflow import LangGraphSupervisor


class WorkflowTest(unittest.TestCase):
    def test_supervisor_runs_end_to_end_with_stub_provider(self) -> None:
        root = Path("tests_runtime") / f"workflow-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            repository = ProjectRepository(root / "test.db")
            storage = ProjectStorage(root / "projects")
            gateway = ModelGateway()
            template_service = TemplateService()
            supervisor = LangGraphSupervisor(repository, storage, gateway, template_service)

            state = ProjectState(
                project_id="project-001",
                request=ProjectCreate(topic="中文文本分类算法"),
            )
            repository.create(state)
            result = supervisor.run(state)

            self.assertEqual(result.status, "completed")
            self.assertTrue(result.literature_records)
            self.assertTrue(result.innovation_candidates)
            self.assertTrue(result.generated_code_files)
            self.assertTrue(result.artifacts.code_zip)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
