from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import uuid

from app.domain import ProjectCreate
from app.template_service import TemplateService


class TemplateServiceTest(unittest.TestCase):
    def test_choose_default_template_for_algorithm(self) -> None:
        service = TemplateService()
        source, manifest = service.choose_default_template(ProjectCreate(topic="图像分类算法"))
        self.assertEqual(source.template_id, "engineering_thesis")
        self.assertIn("第3章 方法设计", manifest.section_mapping)

    def test_parse_user_template_falls_back_without_valid_docx(self) -> None:
        service = TemplateService()
        temp_dir = Path("tests_runtime") / f"template-{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            fake_path = temp_dir / "school-template.docx"
            fake_path.write_bytes(b"not-a-real-docx")
            source, manifest = service.parse_user_template(fake_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        self.assertEqual(source.source_type, "user_upload")
        self.assertEqual(source.template_name, "school-template.docx")
        self.assertTrue(manifest.section_mapping)


if __name__ == "__main__":
    unittest.main()
