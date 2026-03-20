from __future__ import annotations

import unittest
from pathlib import Path
import shutil
from types import SimpleNamespace
import uuid

from app.agents import ReaderAgent, RetrieverAgent, TopicPlannerAgent
from app.domain import ProjectCreate, ProjectState
from app.domain import LiteratureRecord
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
            self.assertTrue(all(record.retrieval_rank >= 1 for record in result.literature_records))
        finally:
            shutil.rmtree(root, ignore_errors=True)

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
