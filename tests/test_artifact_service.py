from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from app.artifact_service import ArtifactService
from app.domain import ProjectCreate, ProjectState, TemplateManifest, TemplateSource
from app.storage import ProjectStorage

try:
    from docx import Document  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    Document = None

try:
    from pptx import Presentation  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    Presentation = None


class ArtifactServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("tests_runtime") / f"artifacts-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.storage = ProjectStorage(self.root / "projects")
        self.service = ArtifactService(self.storage)
        self.manifest = TemplateManifest(
            section_mapping=["封面", "第1章 绪论"],
            style_mapping={
                "title": "Title",
                "chapter": "Heading 1",
                "section": "Heading 2",
                "body": "Normal",
            },
            cover_fields=["学校"],
            figure_slots=["图1"],
            table_slots=["表1"],
            citation_style="GB/T 7714",
            header_footer_rules={"header": "测试模板", "footer": "页码"},
            toc_rules={"enabled": True, "depth": 3},
            ppt_layouts=["title", "content", "summary"],
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    @unittest.skipIf(
        Document is None or Presentation is None,
        "python-docx or python-pptx is not installed in the current environment",
    )
    def test_render_all_uses_valid_word_and_ppt_templates(self) -> None:
        word_template = self.root / "template.docx"
        ppt_template = self.root / "template.pptx"
        template = Document()
        template.add_paragraph("{{cover.题目}}", style="Title")
        template.add_page_break()
        template.add_heading("摘要", level=1)
        template.add_paragraph("{{section.摘要}}")
        template.add_heading("第1章 绪论", level=1)
        template.add_paragraph("{{section.第1章 绪论}}")
        template.save(word_template)
        Presentation().save(ppt_template)

        state = self._build_state(str(word_template), str(ppt_template))

        result = self.service.render_all(state)

        self.assertTrue(Path(result.artifacts.thesis_docx or "").exists())
        self.assertTrue(Path(result.artifacts.defense_pptx or "").exists())
        self.assertEqual(Path(result.artifacts.thesis_docx or "").suffix, ".docx")
        self.assertEqual(Path(result.artifacts.defense_pptx or "").suffix, ".pptx")

        thesis = Document(result.artifacts.thesis_docx)
        texts = [paragraph.text for paragraph in thesis.paragraphs if paragraph.text.strip()]
        self.assertIn("中文文本分类算法", texts)
        self.assertIn("这是论文正文。", texts)
        self.assertNotIn("{{section.第1章 绪论}}", texts)

    def test_render_all_falls_back_when_template_files_are_invalid(self) -> None:
        word_template = self.root / "invalid-template.docx"
        ppt_template = self.root / "invalid-template.pptx"
        word_template.write_text("invalid docx placeholder", encoding="utf-8")
        ppt_template.write_text("invalid pptx placeholder", encoding="utf-8")

        state = self._build_state(str(word_template), str(ppt_template))

        result = self.service.render_all(state)

        self.assertTrue(Path(result.artifacts.thesis_docx or "").exists())
        self.assertTrue(Path(result.artifacts.defense_pptx or "").exists())

    def _build_state(self, word_template_path: str, ppt_template_path: str) -> ProjectState:
        state = ProjectState(
            project_id="project-001",
            request=ProjectCreate(topic="中文文本分类算法"),
        )
        state.template_source = TemplateSource(
            source_type="library_default",
            template_id="engineering_thesis",
            template_name="工科毕业论文",
            template_path=word_template_path,
            ppt_template_path=ppt_template_path,
        )
        state.template_manifest = self.manifest
        state.paper_outline = ["第1章 绪论"]
        state.paper_sections = {"第1章 绪论": "这是论文正文。"}
        state.ppt_outline = ["研究背景", "方法设计", "实验结果"]
        return state


if __name__ == "__main__":
    unittest.main()
