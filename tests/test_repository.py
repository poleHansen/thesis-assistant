from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from app.domain import ProjectCreate, ProjectState
from app.repository import ProjectRepository


class RepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("tests_runtime") / f"repository-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.repository = ProjectRepository(self.root / "test.db")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_list_projects_returns_project_name_from_topic(self) -> None:
        state = ProjectState(
            project_id="project-001",
            request=ProjectCreate(topic="中文文本分类算法"),
        )
        self.repository.create(state)

        projects = self.repository.list_projects()

        self.assertEqual(projects[0]["project_name"], "中文文本分类算法")

    def test_list_projects_falls_back_to_default_name_when_topic_missing(self) -> None:
        state = ProjectState(
            project_id="project-002",
            request=ProjectCreate(topic="占位主题"),
        )
        state.request.topic = ""
        self.repository.create(state)

        projects = self.repository.list_projects()

        self.assertEqual(projects[0]["project_name"], "未命名项目")


if __name__ == "__main__":
    unittest.main()
