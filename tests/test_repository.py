from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from app.domain import InnovationCandidate, ProjectCreate, ProjectState
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

    def test_get_preserves_milestone_two_innovation_fields(self) -> None:
        state = ProjectState(
            project_id="project-003",
            request=ProjectCreate(topic="中文文本分类算法"),
            innovation_candidates=[
                InnovationCandidate(
                    claim="候选 A",
                    supporting_papers=["Paper 1"],
                    contrast_papers=["Paper 2"],
                    analysis_basis=["方法侧证据显示主流路线集中。"],
                    supporting_evidence=["Paper 1：limitations 指向“复现成本较高”"],
                    contrast_evidence=["Paper 2：method 指向“Transformer 编码器”"],
                    novelty_reason="说明",
                    feasibility_score=8.0,
                    risk="低风险",
                    verification_plan="做实验",
                    gap_type="method_gap",
                    rare_reason="较少关注复现成本",
                    recommendation_reason="综合最优",
                    novelty_score=8.4,
                    risk_score=4.0,
                    experiment_cost=4.5,
                    undergrad_fit=8.0,
                    evidence_strength=7.5,
                    evidence_mode="real",
                    overall_score=8.01,
                )
            ],
        )
        state.selected_innovation = state.innovation_candidates[0]
        self.repository.create(state)

        loaded = self.repository.get("project-003")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.selected_innovation.gap_type, "method_gap")
        self.assertEqual(loaded.selected_innovation.evidence_mode, "real")
        self.assertEqual(loaded.selected_innovation.recommendation_reason, "综合最优")
        self.assertTrue(loaded.selected_innovation.analysis_basis)
        self.assertTrue(loaded.selected_innovation.supporting_evidence)

    def test_build_state_accepts_legacy_innovation_candidate_payload(self) -> None:
        request_data = {"topic": "中文文本分类算法"}
        state_data = {
            "project_id": "legacy-project",
            "status": "completed",
            "innovation_candidates": [
                {
                    "claim": "旧版候选",
                    "supporting_papers": ["Paper 1"],
                    "contrast_papers": ["Paper 2"],
                    "novelty_reason": "旧版说明",
                    "feasibility_score": 7.5,
                    "risk": "旧版风险",
                    "verification_plan": "旧版计划",
                }
            ],
        }

        loaded = self.repository._build_state(state_data, request_data)

        self.assertEqual(len(loaded.innovation_candidates), 1)
        self.assertEqual(loaded.innovation_candidates[0].evidence_mode, "fallback")
        self.assertEqual(loaded.innovation_candidates[0].gap_type, "method_gap")
        self.assertEqual(loaded.innovation_candidates[0].analysis_basis, [])


if __name__ == "__main__":
    unittest.main()
