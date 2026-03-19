from __future__ import annotations

from app.domain import TemplateManifest, TemplateSource


DEFAULT_SECTIONS = [
    "封面",
    "摘要",
    "Abstract",
    "目录",
    "第1章 绪论",
    "第2章 相关工作",
    "第3章 方法设计",
    "第4章 实验设计与结果分析",
    "第5章 结论与展望",
    "参考文献",
    "致谢",
]


TEMPLATE_LIBRARY: dict[str, dict[str, object]] = {
    "general_undergraduate": {
        "source": TemplateSource(
            source_type="library_default",
            template_id="general_undergraduate",
            template_name="通用本科论文",
        ),
        "manifest": TemplateManifest(
            section_mapping=DEFAULT_SECTIONS,
            style_mapping={
                "title": "Title",
                "chapter": "Heading 1",
                "section": "Heading 2",
                "body": "Normal",
                "caption": "Caption",
            },
            cover_fields=["学校", "学院", "专业", "题目", "作者", "学号", "指导教师", "日期"],
            figure_slots=["图1", "图2", "图3"],
            table_slots=["表1", "表2", "表3"],
            citation_style="GB/T 7714",
            header_footer_rules={"header": "毕业论文", "footer": "页码居中"},
            toc_rules={"enabled": True, "depth": 3},
            ppt_layouts=["title", "content", "chart", "summary"],
        ),
    },
    "engineering_thesis": {
        "source": TemplateSource(
            source_type="library_default",
            template_id="engineering_thesis",
            template_name="工科毕业论文",
        ),
        "manifest": TemplateManifest(
            section_mapping=DEFAULT_SECTIONS,
            style_mapping={
                "title": "Title",
                "chapter": "Heading 1",
                "section": "Heading 2",
                "body": "Normal",
                "caption": "Caption",
                "code": "Quote",
            },
            cover_fields=["学校", "学院", "专业", "题目", "作者", "学号", "指导教师", "日期"],
            figure_slots=["系统架构图", "实验流程图", "结果对比图"],
            table_slots=["参数表", "对比实验表", "消融实验表"],
            citation_style="GB/T 7714",
            header_footer_rules={"header": "工科毕业设计", "footer": "第 X 页"},
            toc_rules={"enabled": True, "depth": 3},
            ppt_layouts=["title", "problem", "method", "experiment", "result", "summary"],
        ),
    },
    "course_project_report": {
        "source": TemplateSource(
            source_type="library_default",
            template_id="course_project_report",
            template_name="课程设计/实验报告型",
        ),
        "manifest": TemplateManifest(
            section_mapping=[
                "封面",
                "摘要",
                "1. 项目背景",
                "2. 需求分析",
                "3. 系统设计",
                "4. 实验与测试",
                "5. 总结",
                "参考文献",
            ],
            style_mapping={
                "title": "Title",
                "chapter": "Heading 1",
                "section": "Heading 2",
                "body": "Normal",
            },
            cover_fields=["课程名称", "题目", "作者", "班级", "指导教师", "日期"],
            figure_slots=["系统流程图", "功能截图", "结果图"],
            table_slots=["需求表", "测试表"],
            citation_style="GB/T 7714",
            header_footer_rules={"header": "课程设计报告", "footer": "页码右侧"},
            toc_rules={"enabled": True, "depth": 2},
            ppt_layouts=["title", "background", "design", "result", "summary"],
        ),
    },
}

