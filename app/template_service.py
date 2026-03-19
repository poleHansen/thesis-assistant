from __future__ import annotations

from pathlib import Path

from app.domain import ProjectCreate, TemplateManifest, TemplateSource
from app.template_library import TEMPLATE_LIBRARY


class TemplateService:
    def choose_default_template(
        self, request: ProjectCreate
    ) -> tuple[TemplateSource, TemplateManifest]:
        if "课程" in request.school_requirements or "报告" in request.school_requirements:
            key = "course_project_report"
        elif request.paper_type == "algorithm":
            key = "engineering_thesis"
        else:
            key = "general_undergraduate"
        entry = TEMPLATE_LIBRARY[key]
        return entry["source"], entry["manifest"]

    def parse_user_template(
        self, template_path: Path
    ) -> tuple[TemplateSource, TemplateManifest]:
        section_mapping = [
            "封面",
            "摘要",
            "Abstract",
            "目录",
            "引言",
            "相关工作",
            "方法",
            "实验",
            "结论",
            "参考文献",
        ]
        style_mapping = {
            "title": "Title",
            "chapter": "Heading 1",
            "section": "Heading 2",
            "body": "Normal",
            "caption": "Caption",
        }

        try:
            from docx import Document  # type: ignore

            document = Document(str(template_path))
            headings: list[str] = []
            styles_seen: dict[str, str] = {}
            for paragraph in document.paragraphs:
                text = paragraph.text.strip()
                style_name = getattr(paragraph.style, "name", "") or "Normal"
                if style_name.startswith("Heading") and text:
                    headings.append(text)
                if "title" in style_name.lower():
                    styles_seen["title"] = style_name
                elif style_name.startswith("Heading 1"):
                    styles_seen["chapter"] = style_name
                elif style_name.startswith("Heading 2"):
                    styles_seen["section"] = style_name
                elif "caption" in style_name.lower():
                    styles_seen["caption"] = style_name
            if headings:
                section_mapping = headings[:20]
            style_mapping.update(styles_seen)
        except Exception:
            # Fall back to a conservative schema when the parser cannot inspect the template.
            pass

        source = TemplateSource(
            source_type="user_upload",
            template_id=template_path.stem,
            template_name=template_path.name,
            template_path=str(template_path),
        )
        manifest = TemplateManifest(
            section_mapping=section_mapping,
            style_mapping=style_mapping,
            cover_fields=["学校", "学院", "专业", "题目", "作者", "学号", "指导教师", "日期"],
            figure_slots=["图1", "图2", "图3"],
            table_slots=["表1", "表2", "表3"],
            citation_style="GB/T 7714",
            header_footer_rules={"header": "按用户模板输出", "footer": "自动分页"},
            toc_rules={"enabled": True, "depth": 3},
            ppt_layouts=["title", "content", "chart", "summary"],
        )
        return source, manifest

