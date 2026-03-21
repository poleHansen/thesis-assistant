from __future__ import annotations

import unittest
from pathlib import Path
import shutil
from types import SimpleNamespace
import uuid

from app.agents import (
    ConsistencyCheckerAgent,
    CodePlannerAgent,
    ExperimentDesignerAgent,
    FeasibilityReviewerAgent,
    GapAnalystAgent,
    NoveltyJudgeAgent,
    ProcedureWriterAgent,
    ReaderAgent,
    ResultAnalystAgent,
    OutlineWriterAgent,
    RetrieverAgent,
    SectionWriterAgent,
    TopicPlannerAgent,
    CodeAgent,
    ResultSchemaAgent,
    _build_gap_analysis_summary,
    _estimate_candidate_scores,
)
from app.domain import InnovationCandidate, LiteratureRecord, ProjectCreate, ProjectState
from app.model_gateway import ModelGateway
from app.model_settings import ModelSettingsStore
from app.repository import ProjectRepository
from app.storage import ProjectStorage
from app.template_service import TemplateService
from app.workflow import LangGraphSupervisor


class WorkflowTest(unittest.TestCase):
    def test_topic_planner_translates_chinese_topic_into_english_keywords(self) -> None:
        class DummyGateway:
            def complete(self, task_type: str, prompt: str, *, system_prompt: str = ""):
                if "翻译" in prompt:
                    return SimpleNamespace(
                        provider="dummy-translator",
                        model="dummy",
                        content="CLIP-based pavement crack segmentation",
                        fallback_used=False,
                    )
                return SimpleNamespace(
                    provider="dummy-planner",
                    model="dummy",
                    content="clip, pavement crack segmentation, benchmark",
                    fallback_used=False,
                )

        state = ProjectState(
            project_id="project-translate-success",
            request=ProjectCreate(topic="基于CLIP的路面裂缝分割"),
        )

        result = TopicPlannerAgent(DummyGateway()).run(state)

        self.assertEqual(
            result.result_schema.get("translated_topic"),
            "CLIP-based pavement crack segmentation",
        )
        keywords = result.result_schema.get("query_keywords", [])
        self.assertTrue(keywords)
        self.assertEqual(keywords[0], "CLIP-based pavement crack segmentation")
        self.assertTrue(any("pavement" in item.lower() for item in keywords[:3]))
        self.assertFalse(result.result_schema.get("translation_failed"))

    def test_supervisor_runs_end_to_end_with_stub_provider(self) -> None:
        root = Path("tests_runtime") / f"workflow-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            repository = ProjectRepository(root / "test.db")
            storage = ProjectStorage(root / "projects")
            gateway = ModelGateway(ModelSettingsStore.default_settings())
            template_service = TemplateService()
            supervisor = LangGraphSupervisor(repository, storage, gateway, template_service)

            state = ProjectState(
                project_id="project-001",
                request=ProjectCreate(topic="中文文本分类算法"),
            )
            repository.create(state)
            result = supervisor.run(state)

            self.assertEqual(result.status, "completed")
            self.assertGreaterEqual(len(result.literature_records), 2)
            self.assertTrue(result.innovation_candidates)
            self.assertTrue(result.generated_code_files)
            self.assertTrue(result.artifacts.code_zip)
            self.assertTrue(result.survey_table)
            self.assertTrue(result.retrieval_diagnostics)
            self.assertTrue(all(record.problem for record in result.literature_records))
            self.assertTrue(all(record.method for record in result.literature_records))
            self.assertTrue(all("confidence" in row for row in result.survey_table))
            self.assertTrue(all("needs_review" in row for row in result.survey_table))
            self.assertTrue(all(record.retrieval_rank >= 1 for record in result.literature_records))
            self.assertIn(result.retrieval_summary.retrieval_status, {"success", "partial", "fallback"})
            self.assertGreaterEqual(len(result.innovation_candidates), 3)
            self.assertTrue(all(item.supporting_papers for item in result.innovation_candidates))
            self.assertTrue(all(item.contrast_papers for item in result.innovation_candidates))
            self.assertTrue(all(item.gap_type for item in result.innovation_candidates))
            self.assertTrue(result.selected_innovation)
            self.assertTrue(result.selected_innovation.recommendation_reason)
            self.assertIn(result.selected_innovation.evidence_mode, {"real", "fallback"})
            self.assertTrue(result.artifacts.innovation_report)
            self.assertTrue(result.audit_trail)
            self.assertTrue(result.checkpoints)
            self.assertIn(result.workflow_outcome, {"success", "partial_success", "rollback_success"})
            self.assertEqual(result.workflow_phase, "completed")
            self.assertIn("consistency_summary", result.result_schema)
            self.assertIn("findings", result.result_schema["consistency_summary"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_supervisor_records_rollback_when_review_has_blockers(self) -> None:
        class RollbackSupervisor(LangGraphSupervisor):
            def __init__(self, repository, storage, gateway, template_service) -> None:
                super().__init__(repository, storage, gateway, template_service)
                self._review_probe_count = 0

            def _review_has_blockers(self, state: ProjectState) -> bool:
                self._review_probe_count += 1
                if self._review_probe_count == 1:
                    return True
                return False

        root = Path("tests_runtime") / f"workflow-rollback-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            repository = ProjectRepository(root / "test.db")
            storage = ProjectStorage(root / "projects")
            gateway = ModelGateway(ModelSettingsStore.default_settings())
            template_service = TemplateService()
            supervisor = RollbackSupervisor(repository, storage, gateway, template_service)

            state = ProjectState(
                project_id="project-rollback-001",
                request=ProjectCreate(topic="中文文本分类算法"),
            )
            repository.create(state)

            result = supervisor.run(state)

            self.assertTrue(result.rollback_history)
            self.assertTrue(any(item.to_phase == "writing_delivery" for item in result.rollback_history))
            self.assertTrue(any(event.level in {"warning", "error"} for event in result.audit_trail))
            self.assertIn(result.workflow_outcome, {"partial_success", "rollback_success"})
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_gap_analyst_generates_gap_typed_candidates_with_evidence(self) -> None:
        records = [
            LiteratureRecord(
                source="semantic_scholar",
                title=f"Paper {index}",
                authors="Tester",
                year=2025,
                abstract="Abstract",
                doi_or_url=f"https://example.com/{index}",
                problem="中文文本分类",
                method="Transformer 编码器, 轻量分类头" if index < 3 else "CNN 编码器, 注意力层",
                dataset="THUCNews, Fudan" if index % 2 else "THUCNews",
                metrics="Accuracy, F1",
                conclusion="方法有效",
                limitations="缺少鲁棒性评测, 缺少低资源场景验证",
                confidence_score=0.8,
            )
            for index in range(1, 6)
        ]
        state = ProjectState(
            project_id="project-gap-analysis",
            request=ProjectCreate(topic="中文文本分类算法"),
            literature_records=records,
        )

        result = GapAnalystAgent(ModelGateway(ModelSettingsStore.default_settings())).run(state)

        self.assertGreaterEqual(len(result.innovation_candidates), 3)
        self.assertTrue(all(candidate.supporting_papers for candidate in result.innovation_candidates))
        self.assertTrue(all(candidate.contrast_papers for candidate in result.innovation_candidates))
        self.assertTrue(all(candidate.gap_type for candidate in result.innovation_candidates))
        self.assertTrue(all(candidate.evidence_mode == "real" for candidate in result.innovation_candidates))
        self.assertTrue(all(candidate.analysis_basis for candidate in result.innovation_candidates))
        self.assertTrue(all(candidate.supporting_evidence for candidate in result.innovation_candidates))
        self.assertIn("gap_analysis", result.result_schema)
        self.assertTrue(result.result_schema["gap_analysis"].get("method_gaps"))
        self.assertTrue(result.result_schema["gap_analysis"].get("support_evidence_map"))
        self.assertTrue(result.result_schema.get("gap_analysis_overview"))

    def test_gap_analysis_summary_contains_structured_gap_and_evidence_maps(self) -> None:
        records = [
            LiteratureRecord(
                source="semantic_scholar",
                title=f"Paper {index}",
                authors="Tester",
                year=2025,
                abstract="Abstract",
                doi_or_url=f"https://example.com/{index}",
                problem="中文文本分类标准设置" if index < 3 else "中文文本分类跨域部署",
                method="Transformer 编码器, 轻量分类头" if index < 3 else "CNN 编码器, 对比学习模块",
                dataset="THUCNews" if index < 4 else "Fudan",
                metrics="Accuracy, F1" if index < 4 else "Accuracy, F1, Robustness",
                conclusion="方法有效",
                limitations="缺少鲁棒性评测, 缺少低资源场景验证" if index % 2 else "样本增强不足, 部署成本较高",
                confidence_score=0.82,
            )
            for index in range(1, 6)
        ]
        state = ProjectState(
            project_id="project-gap-summary",
            request=ProjectCreate(topic="中文文本分类算法"),
            literature_records=records,
        )

        summary = _build_gap_analysis_summary(state)

        self.assertEqual(summary.get("mode"), "real")
        self.assertTrue(summary.get("method_gaps"))
        self.assertTrue(summary.get("data_gaps"))
        self.assertTrue(summary.get("scenario_gaps"))
        self.assertTrue(summary.get("evaluation_gaps"))
        self.assertTrue(summary.get("support_evidence_map", {}).get("methods"))
        self.assertTrue(summary.get("contrast_evidence_map", {}).get("metrics"))

    def test_consistency_checker_builds_structured_findings(self) -> None:
        state = ProjectState(
            project_id="project-consistency-findings",
            request=ProjectCreate(topic="中文文本分类算法"),
        )
        state.experiment_plan = ExperimentDesignerAgent(ModelGateway(ModelSettingsStore.default_settings())).run(state).experiment_plan
        state.generated_code_files["README.md"] = "# Demo\n"
        state.generated_code_files["configs/default.yaml"] = "seed: 42\nresult_dir: results\n"
        state.result_schema["procedure_document"] = "实验目的\n"
        state.paper_sections = {"实验": "实验部分待补充", "参考文献": ""}
        state.ppt_outline = ["封面", "方法设计"]
        state.result_schema["ppt_section_mapping"] = {"方法设计": "方法章节"}

        result = ConsistencyCheckerAgent(ModelGateway(ModelSettingsStore.default_settings())).run(state)
        summary = result.result_schema["consistency_summary"]

        self.assertTrue(summary.get("findings"))
        self.assertGreater(summary.get("blocking_count", 0), 0)
        self.assertTrue(any(not item["aligned"] for item in summary["findings"]))

    def test_estimate_candidate_scores_prefers_real_evidence_over_fallback(self) -> None:
        support_records = [
            LiteratureRecord(
                source="semantic_scholar",
                title="Paper A",
                authors="Tester",
                year=2025,
                abstract="Abstract",
                doi_or_url="https://example.com/a",
                problem="中文文本分类",
                method="Transformer 编码器",
                dataset="THUCNews",
                metrics="Accuracy, F1",
                conclusion="方法有效",
                limitations="缺少鲁棒性评测",
                confidence_score=0.86,
            ),
            LiteratureRecord(
                source="semantic_scholar",
                title="Paper B",
                authors="Tester",
                year=2025,
                abstract="Abstract",
                doi_or_url="https://example.com/b",
                problem="中文文本分类",
                method="Transformer 编码器, 轻量分类头",
                dataset="THUCNews",
                metrics="Accuracy, F1",
                conclusion="方法有效",
                limitations="复现成本较高",
                confidence_score=0.81,
            ),
        ]
        contrast_records = [
            LiteratureRecord(
                source="semantic_scholar",
                title="Paper C",
                authors="Tester",
                year=2025,
                abstract="Abstract",
                doi_or_url="https://example.com/c",
                problem="中文文本分类",
                method="CNN",
                dataset="Fudan",
                metrics="Accuracy",
                conclusion="方法有效",
                limitations="局限较少",
                confidence_score=0.7,
            )
        ]
        summary = {
            "common_metrics": ["Accuracy", "F1"],
            "needs_review_count": 0,
            "method_gaps": [{"scarcity_score": 8.0, "coverage_score": 7.5}],
        }

        real_scores = _estimate_candidate_scores("method_gap", "real", support_records, contrast_records, summary)
        fallback_scores = _estimate_candidate_scores("method_gap", "fallback", support_records[:1], contrast_records, summary)

        self.assertGreater(real_scores["evidence_strength"], fallback_scores["evidence_strength"])
        self.assertGreater(real_scores["novelty_score"], fallback_scores["novelty_score"])
        self.assertLess(real_scores["risk_score"], fallback_scores["risk_score"])

    def test_experiment_designer_populates_milestone_three_fields(self) -> None:
        state = ProjectState(
            project_id="project-plan-fields",
            request=ProjectCreate(topic="中文文本分类算法", paper_type="algorithm"),
            literature_records=[
                LiteratureRecord(
                    source="semantic_scholar",
                    title="Paper A",
                    authors="Tester",
                    year=2025,
                    abstract="Abstract",
                    doi_or_url="https://example.com/a",
                    problem="中文文本分类",
                    method="Transformer 编码器",
                    dataset="THUCNews, Fudan",
                    metrics="Accuracy, F1",
                    conclusion="方法有效",
                    limitations="缺少鲁棒性评测",
                    confidence_score=0.82,
                )
            ],
            selected_innovation=InnovationCandidate(
                claim="面向中文文本分类的轻量增强方案",
                supporting_papers=["Paper A"],
                contrast_papers=[],
                novelty_reason="有效",
                feasibility_score=8.0,
                risk="可控",
                verification_plan="补充对比实验",
            ),
        )

        planned = ExperimentDesignerAgent(ModelGateway(ModelSettingsStore.default_settings())).run(state)

        self.assertTrue(planned.experiment_plan)
        assert planned.experiment_plan is not None
        self.assertTrue(planned.experiment_plan.parameters)
        self.assertTrue(planned.experiment_plan.run_commands.get("train"))
        self.assertIn("results/eval_metrics.json", planned.experiment_plan.result_files)
        self.assertTrue(planned.experiment_plan.evidence_links)
        self.assertIn("milestone_three_contract", planned.result_schema)

    def test_procedure_and_code_agent_keep_commands_and_result_files_consistent(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-procedure-code",
            request=ProjectCreate(topic="中文文本分类算法"),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state = ProcedureWriterAgent(gateway).run(state)
        state = ResultSchemaAgent(gateway).run(state)
        state = CodeAgent(gateway).run(state)

        procedure = str(state.result_schema.get("procedure_document", ""))
        readme = state.generated_code_files.get("README.md", "")
        assert state.experiment_plan is not None
        for command in state.experiment_plan.run_commands.values():
            self.assertIn(command, procedure)
            self.assertIn(command, readme)
        for result_file in state.experiment_plan.result_files:
            self.assertIn(result_file, procedure)
            self.assertIn(result_file, readme)
        self.assertTrue(all(path in state.generated_code_files for path in [
            "train.py",
            "eval.py",
            "infer.py",
            "configs/default.yaml",
            "src/model.py",
            "src/data.py",
            "README.md",
            "requirements.txt",
        ]))
        self.assertIn("dataset_path", state.generated_code_files["configs/default.yaml"])
        self.assertIn("建议额外整理 1 份主结果表", procedure)
        self.assertIn("dataset_path、text_key、label_key", procedure)
        self.assertIn("data/dataset.jsonl", readme)
        self.assertIn("results/model_state.json", readme)

    def test_code_agent_generates_executable_mvp_pipeline_files(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-code-mvp",
            request=ProjectCreate(topic="中文文本分类算法"),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state = CodePlannerAgent(gateway).run(state)
        state = CodeAgent(gateway).run(state)

        train_code = state.generated_code_files["train.py"]
        eval_code = state.generated_code_files["eval.py"]
        infer_code = state.generated_code_files["infer.py"]
        model_code = state.generated_code_files["src/model.py"]
        data_code = state.generated_code_files["src/data.py"]

        self.assertIn("argparse", train_code)
        self.assertIn("model.save", train_code)
        self.assertIn("split_dataset", train_code)
        self.assertIn("ThesisModel.load", eval_code)
        self.assertIn("--text", infer_code)
        self.assertIn("class_profiles", model_code)
        self.assertIn("ensure_dataset", data_code)
        self.assertIn("data/dataset.jsonl", state.generated_code_files)

    def test_result_analyst_populates_structured_result_payload(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-result-analyst",
            request=ProjectCreate(topic="中文文本分类算法", delivery_mode="final"),
            selected_innovation=InnovationCandidate(
                claim="面向中文文本分类的轻量增强方案",
                supporting_papers=["Paper A"],
                contrast_papers=["Paper B"],
                novelty_reason="有效",
                feasibility_score=8.0,
                risk="可控",
                verification_plan="补充对比实验",
            ),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state = ResultSchemaAgent(gateway).run(state)
        state = ResultAnalystAgent(gateway).run(state)

        self.assertTrue(state.result_schema.get("result_tables"))
        self.assertTrue(state.result_schema.get("result_figures"))
        self.assertTrue(state.result_schema.get("result_analysis_text"))
        self.assertTrue(state.result_schema.get("result_summary_for_paper"))
        self.assertTrue(state.result_schema.get("result_summary_for_ppt"))
        self.assertTrue(state.result_schema.get("result_key_findings"))
        first_table = state.result_schema.get("result_tables", [])[0]
        self.assertIn("rows", first_table)
        self.assertIn("summary", first_table)

    def test_result_analyst_uses_fill_in_template_in_draft_mode(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-result-analyst-draft",
            request=ProjectCreate(topic="中文文本分类算法", delivery_mode="draft"),
            selected_innovation=InnovationCandidate(
                claim="面向中文文本分类的轻量增强方案",
                supporting_papers=["Paper A"],
                contrast_papers=["Paper B"],
                novelty_reason="有效",
                feasibility_score=8.0,
                risk="可控",
                verification_plan="补充对比实验",
            ),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state = ResultSchemaAgent(gateway).run(state)
        state = ResultAnalystAgent(gateway).run(state)

        self.assertIn("用户完成实验后回填", str(state.result_schema.get("result_analysis_text", "")))
        first_table = state.result_schema.get("result_tables", [])[0]
        self.assertEqual(first_table.get("title"), "实验结果记录模板")
        self.assertEqual(first_table.get("source"), "manual_fill")

    def test_consistency_summary_contains_granular_checks_and_mapping_status(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-consistency-granular",
            request=ProjectCreate(topic="中文文本分类算法"),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state = ProcedureWriterAgent(gateway).run(state)
        state = ResultSchemaAgent(gateway).run(state)
        state = ResultAnalystAgent(gateway).run(state)
        state = CodeAgent(gateway).run(state)
        state.paper_outline = ["实验"]
        state.paper_sections = {
            "实验": str(state.result_schema.get("result_summary_for_paper", ""))
        }
        state.result_schema["ppt_section_mapping"] = {
            "方法设计": "方法章节",
            "实验设置": "实验章节",
            "结果分析": "实验章节/结果分析段",
            "结论与展望": "结论章节",
        }

        reviewed = ConsistencyCheckerAgent(gateway).run(state)

        summary = reviewed.result_schema.get("consistency_summary", {})
        checks = summary.get("checks", [])
        self.assertTrue(summary.get("plan_config_aligned"))
        self.assertTrue(summary.get("ppt_mapping_aligned"))
        self.assertEqual(len(checks), 7)
        self.assertTrue(all("label" in item and "detail" in item for item in checks))
        self.assertIn("findings", summary)
        self.assertEqual(summary.get("total_checks"), 7)
        first_finding = summary.get("findings", [])[0]
        self.assertIn("diffs", first_finding)
        self.assertIn("locations", first_finding)

    def test_consistency_summary_exposes_field_level_diffs(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-consistency-diffs",
            request=ProjectCreate(topic="中文文本分类算法"),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state.generated_code_files["README.md"] = "# Demo\n- python train.py --config configs/default.yaml\n"
        state.generated_code_files["configs/default.yaml"] = "seed: 42\nresult_dir: results\n"
        state.result_schema["procedure_document"] = "实验目的\n- python train.py --config configs/default.yaml\n"
        state.paper_sections = {"实验": "仅包含实验摘要", "参考文献": ""}
        state.ppt_outline = ["封面", "方法设计"]
        state.result_schema["ppt_section_mapping"] = {"方法设计": "方法章节"}

        reviewed = ConsistencyCheckerAgent(gateway).run(state)
        summary = reviewed.result_schema.get("consistency_summary", {})
        blocking = [item for item in summary.get("findings", []) if item.get("blocking")]

        self.assertTrue(blocking)
        self.assertTrue(any(item.get("diffs") for item in blocking))
        self.assertTrue(any(item.get("locations") for item in blocking))

    def test_section_writer_reuses_structured_result_content_in_experiment_section(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-paper-sections",
            request=ProjectCreate(topic="道路裂缝检测", delivery_mode="final"),
            selected_innovation=InnovationCandidate(
                claim="基于 YOLO 的裂缝检测增强方案",
                supporting_papers=["Paper A"],
                contrast_papers=["Paper B"],
                novelty_reason="有效",
                feasibility_score=8.0,
                risk="可控",
                verification_plan="补充实验",
            ),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state = ProcedureWriterAgent(gateway).run(state)
        state = ResultSchemaAgent(gateway).run(state)
        state = ResultAnalystAgent(gateway).run(state)
        state.paper_outline = ["摘要", "第4章 实验结果与分析", "结论"]

        state = SectionWriterAgent(gateway).run(state)

        experiment_text = state.paper_sections.get("第4章 实验结果与分析", "")
        self.assertIn(str(state.result_schema.get("result_summary_for_paper", "")), experiment_text)
        self.assertIn("主结果对比表", experiment_text)
        self.assertIn("训练曲线", experiment_text)

    def test_section_writer_in_draft_mode_avoids_unverified_result_claims(self) -> None:
        gateway = ModelGateway(ModelSettingsStore.default_settings())
        state = ProjectState(
            project_id="project-paper-sections-draft",
            request=ProjectCreate(topic="道路裂缝检测", delivery_mode="draft"),
            selected_innovation=InnovationCandidate(
                claim="基于 YOLO 的裂缝检测增强方案",
                supporting_papers=["Paper A"],
                contrast_papers=["Paper B"],
                novelty_reason="有效",
                feasibility_score=8.0,
                risk="可控",
                verification_plan="补充实验",
            ),
        )
        state = ExperimentDesignerAgent(gateway).run(state)
        state = ProcedureWriterAgent(gateway).run(state)
        state = ResultSchemaAgent(gateway).run(state)
        state = ResultAnalystAgent(gateway).run(state)
        state.paper_outline = ["摘要", "第4章 实验结果与分析", "结论"]

        state = SectionWriterAgent(gateway).run(state)

        experiment_text = state.paper_sections.get("第4章 实验结果与分析", "")
        self.assertIn("真实实验结果、结果表和图表由用户完成实验后补充", experiment_text)
        self.assertNotIn("主结果对比表", experiment_text)

    def test_gap_analyst_falls_back_when_structured_evidence_is_insufficient(self) -> None:
        state = ProjectState(
            project_id="project-gap-fallback",
            request=ProjectCreate(topic="中文文本分类算法"),
            literature_records=[
                LiteratureRecord(
                    source="fallback",
                    title="Fallback Paper",
                    authors="Tester",
                    year=2025,
                    abstract="Abstract",
                    doi_or_url="https://example.com/fallback",
                    problem="中文文本分类",
                    method="Transformer",
                    dataset="THUCNews",
                    metrics="Accuracy",
                    conclusion="需要进一步验证",
                    limitations="信息不足",
                    is_fallback=True,
                    confidence_score=0.2,
                )
            ],
        )

        result = GapAnalystAgent(ModelGateway(ModelSettingsStore.default_settings())).run(state)

        self.assertGreaterEqual(len(result.innovation_candidates), 3)
        self.assertTrue(all(candidate.evidence_mode == "fallback" for candidate in result.innovation_candidates))
        self.assertTrue(all(not candidate.analysis_basis for candidate in result.innovation_candidates))
        self.assertEqual(result.result_schema.get("gap_analysis", {}).get("mode"), "fallback")

    def test_novelty_judge_uses_multidimensional_scores_not_only_feasibility(self) -> None:
        state = ProjectState(
            project_id="project-ranking",
            request=ProjectCreate(topic="中文文本分类算法"),
            innovation_candidates=[
                InnovationCandidate(
                    claim="候选 A",
                    supporting_papers=["Paper 1", "Paper 2"],
                    contrast_papers=["Paper 3"],
                    novelty_reason="新颖性高",
                    feasibility_score=7.0,
                    risk="中等风险",
                    verification_plan="做对照实验",
                    gap_type="method_gap",
                    novelty_score=9.0,
                    risk_score=4.0,
                    experiment_cost=4.0,
                    undergrad_fit=8.5,
                    evidence_strength=8.5,
                    evidence_mode="real",
                ),
                InnovationCandidate(
                    claim="候选 B",
                    supporting_papers=["Paper 1"],
                    contrast_papers=["Paper 4"],
                    novelty_reason="可行性高",
                    feasibility_score=9.5,
                    risk="风险较高",
                    verification_plan="直接训练",
                    gap_type="data_gap",
                    novelty_score=5.5,
                    risk_score=7.0,
                    experiment_cost=7.5,
                    undergrad_fit=5.5,
                    evidence_strength=4.5,
                    evidence_mode="fallback",
                ),
            ],
        )

        judged = NoveltyJudgeAgent(ModelGateway(ModelSettingsStore.default_settings())).run(state)

        self.assertEqual(judged.selected_innovation.claim, "候选 A")
        self.assertGreater(judged.innovation_candidates[0].overall_score, judged.innovation_candidates[1].overall_score)
        self.assertTrue(judged.selected_innovation.recommendation_reason)
        self.assertIn("依据为", judged.selected_innovation.recommendation_reason)

    def test_feasibility_reviewer_warns_for_fallback_and_low_evidence(self) -> None:
        state = ProjectState(
            project_id="project-feasibility-review",
            request=ProjectCreate(topic="中文文本分类算法"),
            innovation_candidates=[
                InnovationCandidate(
                    claim="候选 C",
                    supporting_papers=["Paper 1"],
                    contrast_papers=["Paper 2"],
                    novelty_reason="占位推荐",
                    feasibility_score=6.5,
                    risk="风险较高",
                    verification_plan="补实验",
                    gap_type="evaluation_gap",
                    novelty_score=6.0,
                    risk_score=8.0,
                    experiment_cost=6.0,
                    undergrad_fit=5.0,
                    evidence_strength=4.0,
                    evidence_mode="fallback",
                ),
                InnovationCandidate(
                    claim="候选 D",
                    supporting_papers=["Paper 3", "Paper 4"],
                    contrast_papers=["Paper 5"],
                    novelty_reason="真实推荐",
                    feasibility_score=7.8,
                    risk="低风险",
                    verification_plan="补对照实验",
                    gap_type="method_gap",
                    novelty_score=7.5,
                    risk_score=4.5,
                    experiment_cost=5.0,
                    undergrad_fit=7.0,
                    evidence_strength=6.8,
                    evidence_mode="real",
                ),
            ],
            selected_innovation=InnovationCandidate(
                claim="候选 C",
                supporting_papers=["Paper 1"],
                contrast_papers=["Paper 2"],
                novelty_reason="占位推荐",
                feasibility_score=6.5,
                risk="风险较高",
                verification_plan="补实验",
                gap_type="evaluation_gap",
                novelty_score=6.0,
                risk_score=8.0,
                experiment_cost=6.0,
                undergrad_fit=5.0,
                evidence_strength=4.0,
                evidence_mode="fallback",
            ),
        )

        reviewed = FeasibilityReviewerAgent(ModelGateway(ModelSettingsStore.default_settings())).run(state)

        self.assertGreaterEqual(len(reviewed.warnings), 3)
        self.assertTrue(any("fallback" in warning for warning in reviewed.warnings))
        self.assertTrue(any("第二候选" in warning for warning in reviewed.warnings))

    def test_reader_agent_merges_llm_structured_fields(self) -> None:
        class DummyGateway:
            def complete(self, task_type: str, prompt: str, *, system_prompt: str = ""):
                return SimpleNamespace(
                    provider="dummy",
                    model="dummy-reader",
                    content=(
                        '{"problem":"情感分类任务","method":"层次注意力网络","dataset":"ChnSentiCorp",'
                        '"metrics":"Accuracy, F1","conclusion":"显著优于基线",'
                        '"limitations":"跨域泛化不足","evidence_source":"abstract",'
                        '"confidence_score":0.93,"evidence_quote":"We propose a hierarchical attention network."}'
                    ),
                    fallback_used=False,
                )

        state = ProjectState(
            project_id="project-llm-reader",
            request=ProjectCreate(topic="中文情感分析"),
            literature_records=[
                LiteratureRecord(
                    source="semantic_scholar",
                    title="Hierarchical Attention for Sentiment Classification",
                    authors="Tester",
                    year=2025,
                    abstract=(
                        "This paper studies sentiment classification problem. "
                        "We propose a hierarchical attention network and evaluate on ChnSentiCorp "
                        "with Accuracy and F1. Results show strong improvements but cross-domain generalization is limited."
                    ),
                    doi_or_url="https://example.com/paper",
                )
            ],
        )

        result = ReaderAgent(DummyGateway()).run(state)

        self.assertEqual(result.literature_records[0].problem, "情感分类任务")
        self.assertEqual(result.literature_records[0].method, "层次注意力网络")
        self.assertEqual(result.literature_records[0].dataset, "ChnSentiCorp")
        self.assertEqual(result.literature_records[0].evidence_quote, "We propose a hierarchical attention network.")
        self.assertGreaterEqual(result.literature_records[0].confidence_score, 0.93)
        self.assertFalse(result.literature_records[0].needs_review)

    def test_reader_agent_sanitizes_invalid_evidence_fields(self) -> None:
        class DummyGateway:
            def complete(self, task_type: str, prompt: str, *, system_prompt: str = ""):
                return SimpleNamespace(
                    provider="dummy",
                    model="dummy-reader",
                    content=(
                        '{"problem":"图像分类","method":"轻量网络","dataset":"CIFAR-10",'
                        '"metrics":"Accuracy","conclusion":"有效","limitations":"待验证",'
                        '"evidence_source":"hallucinated","confidence_score":1.8,"evidence_quote":""}'
                    ),
                    fallback_used=False,
                )

        state = ProjectState(
            project_id="project-reader-validation",
            request=ProjectCreate(topic="图像分类"),
            literature_records=[
                LiteratureRecord(
                    source="semantic_scholar",
                    title="Lightweight Image Classification",
                    authors="Tester",
                    year=2025,
                    abstract="This paper studies image classification and proposes a lightweight network on CIFAR-10.",
                    doi_or_url="https://example.com/image",
                )
            ],
        )

        result = ReaderAgent(DummyGateway()).run(state)

        self.assertEqual(result.literature_records[0].evidence_source, "abstract")
        self.assertLessEqual(result.literature_records[0].confidence_score, 1.0)
        self.assertTrue(result.literature_records[0].needs_review)

    def test_retriever_records_failure_diagnostics_before_fallback(self) -> None:
        class FailingRetriever(RetrieverAgent):
            def _search_openalex(self, query: str, original_query: str, query_language: str):
                return [], self._build_diagnostic("openalex", query, False, 0, "timeout", original_query, query_language)

            def _search_arxiv(self, query: str, original_query: str, query_language: str):
                return [], self._build_diagnostic("arxiv", query, False, 0, "ssl blocked", original_query, query_language)

            def _search_semantic_scholar(self, query: str, original_query: str, query_language: str):
                return [], self._build_diagnostic("semantic_scholar", query, False, 0, "rate limited", original_query, query_language)

        state = ProjectState(
            project_id="project-retrieval-diag",
            request=ProjectCreate(topic="中文文本分类算法"),
            result_schema={
                "translated_topic": "Chinese text classification algorithms",
                "query_keywords": ["Chinese text classification algorithms", "text classification"],
            },
        )

        result = FailingRetriever(ModelGateway(ModelSettingsStore.default_settings())).run(state)

        self.assertTrue(result.retrieval_diagnostics)
        self.assertTrue(all(not item["ok"] for item in result.retrieval_diagnostics))
        self.assertTrue(all(item["query_language"] == "english" for item in result.retrieval_diagnostics))
        self.assertTrue(any("openalex" in warning.lower() for warning in result.warnings))
        self.assertTrue(any(record.is_fallback for record in result.literature_records))
        self.assertEqual(result.retrieval_summary.retrieval_status, "fallback")

    def test_retriever_requires_five_valid_papers_for_success(self) -> None:
        class PartiallySuccessfulRetriever(RetrieverAgent):
            def __init__(self) -> None:
                self.gateway = ModelGateway(ModelSettingsStore.default_settings())
                self.queries_seen: list[str] = []

            def _search_openalex(self, query: str, original_query: str, query_language: str):
                self.queries_seen.append(query)
                if query == "q1":
                    records = [
                        LiteratureRecord(
                            source="openalex",
                            title=f"Paper {index}",
                            authors="Tester",
                            year=2025,
                            abstract="Abstract available",
                            doi_or_url=f"https://example.com/{index}",
                        )
                        for index in range(1, 3)
                    ]
                elif query == "q2":
                    records = [
                        LiteratureRecord(
                            source="openalex",
                            title=f"Paper {index}",
                            authors="Tester",
                            year=2025,
                            abstract="Abstract available",
                            doi_or_url=f"https://example.com/{index}",
                        )
                        for index in range(3, 5)
                    ]
                else:
                    records = []
                return records, self._build_diagnostic("openalex", query, True, len(records), "", original_query, query_language)

            def _search_arxiv(self, query: str, original_query: str, query_language: str):
                return [], self._build_diagnostic("arxiv", query, True, 0, "", original_query, query_language)

            def _search_semantic_scholar(self, query: str, original_query: str, query_language: str):
                if query == "q3":
                    records = [
                        LiteratureRecord(
                            source="semantic_scholar",
                            title="Paper 5",
                            authors="Tester",
                            year=2025,
                            abstract="Abstract available",
                            doi_or_url="https://example.com/5",
                        )
                    ]
                else:
                    records = []
                return records, self._build_diagnostic("semantic_scholar", query, True, len(records), "", original_query, query_language)

        state = ProjectState(
            project_id="project-retrieval-success-threshold",
            request=ProjectCreate(topic="中文文本分类算法"),
            result_schema={
                "translated_topic": "Chinese text classification algorithms",
                "query_keywords": ["q1", "q2", "q3", "q4"],
            },
        )

        result = PartiallySuccessfulRetriever().run(state)

        self.assertEqual(result.retrieval_summary.valid_paper_count, 5)
        self.assertEqual(result.retrieval_summary.retrieval_status, "success")
        self.assertEqual(result.retrieval_summary.fallback_count, 0)
        self.assertEqual(result.literature_records[-1].title, "Paper 5")

    def test_topic_translation_failure_falls_back_to_original_query(self) -> None:
        class InvalidTranslationGateway:
            def complete(self, task_type: str, prompt: str, *, system_prompt: str = ""):
                if "翻译" in prompt:
                    return SimpleNamespace(
                        provider="dummy-translator",
                        model="dummy",
                        content="基于CLIP的路面裂缝分割",
                        fallback_used=False,
                    )
                return SimpleNamespace(
                    provider="dummy-planner",
                    model="dummy",
                    content="trace",
                    fallback_used=False,
                )

        state = ProjectState(
            project_id="project-translate-fallback",
            request=ProjectCreate(topic="基于CLIP的路面裂缝分割"),
        )

        result = TopicPlannerAgent(InvalidTranslationGateway()).run(state)

        self.assertEqual(result.result_schema.get("translated_topic"), "基于CLIP的路面裂缝分割")
        self.assertTrue(result.result_schema.get("translation_failed"))
        self.assertTrue(any("翻译结果不可用" in item for item in result.warnings))
        self.assertEqual(result.result_schema.get("query_keywords", [""])[0], "基于CLIP的路面裂缝分割")


if __name__ == "__main__":
    unittest.main()
