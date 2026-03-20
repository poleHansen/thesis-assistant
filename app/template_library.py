from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import SETTINGS


@dataclass(frozen=True, slots=True)
class TemplateBundle:
    template_id: str
    template_name: str
    directory: Path

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    @property
    def word_template_path(self) -> Path:
        return self.directory / "word" / "template.docx"

    @property
    def ppt_template_path(self) -> Path:
        return self.directory / "ppt" / "template.pptx"


TEMPLATE_REGISTRY = {
    "general_undergraduate": "通用本科论文",
    "engineering_thesis": "工科毕业论文",
    "course_project_report": "课程设计/实验报告型",
}


def build_template_library(root: Path | None = None) -> dict[str, TemplateBundle]:
    SETTINGS.ensure_directories()
    base_dir = root or SETTINGS.template_library_dir
    return {
        template_id: TemplateBundle(
            template_id=template_id,
            template_name=template_name,
            directory=base_dir / template_id,
        )
        for template_id, template_name in TEMPLATE_REGISTRY.items()
    }


TEMPLATE_LIBRARY = build_template_library()
