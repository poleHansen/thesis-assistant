from __future__ import annotations

import csv
import json
import re
import textwrap
import zipfile
from pathlib import Path

from app.domain import ArtifactBundle, ProjectState, TemplateManifest
from app.storage import ProjectStorage


class ArtifactService:
    def __init__(self, storage: ProjectStorage) -> None:
        self.storage = storage

    def render_all(self, state: ProjectState) -> ProjectState:
        artifacts_dir = self.storage.ensure_project_tree(state.project_id) / "artifacts"
        reports_dir = artifacts_dir / "reports"
        code_dir = artifacts_dir / "code"
        slides_dir = artifacts_dir / "slides"
        reports_dir.mkdir(parents=True, exist_ok=True)
        code_dir.mkdir(parents=True, exist_ok=True)
        slides_dir.mkdir(parents=True, exist_ok=True)

        state.artifacts = ArtifactBundle(
            literature_review=self._write_literature_review(reports_dir, state),
            innovation_report=self._write_text(
                reports_dir / "innovation_report.md",
                self._innovation_report(state),
            ),
            experiment_plan=self._write_docx_like(
                reports_dir / "experiment_plan.docx",
                self._experiment_plan_text(state),
            ),
            procedure=self._write_docx_like(
                reports_dir / "procedure.docx",
                state.result_schema.get("procedure_document", ""),
            ),
            thesis_docx=self._write_docx_like(
                reports_dir / "thesis.docx",
                self._thesis_text(state),
            ),
            thesis_pdf=self._write_minimal_pdf(
                reports_dir / "thesis.pdf",
                self._thesis_text(state),
            ),
            code_zip=self._write_code_zip(code_dir / "code_bundle.zip", state),
            defense_pptx=self._write_pptx_like(
                slides_dir / "defense.pptx",
                self._ppt_text(state),
            ),
            qa_report=self._write_text(
                reports_dir / "qa_report.json",
                json.dumps(
                    {"findings": state.review_findings, "warnings": state.warnings},
                    ensure_ascii=False,
                    indent=2,
                ),
            ),
        )
        return state

    def _write_literature_review(self, reports_dir: Path, state: ProjectState) -> str:
        try:
            from openpyxl import Workbook  # type: ignore

            path = reports_dir / "literature_review.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "literature"
            headers = [
                "title",
                "problem",
                "method",
                "dataset",
                "metrics",
                "conclusion",
                "limitations",
            ]
            sheet.append(headers)
            for row in state.survey_table:
                sheet.append([row.get(header, "") for header in headers])
            workbook.save(path)
            return str(path)
        except Exception:
            path = reports_dir / "literature_review.csv"
            headers = [
                "title",
                "problem",
                "method",
                "dataset",
                "metrics",
                "conclusion",
                "limitations",
            ]
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerows(state.survey_table)
            return str(path)

    def _innovation_report(self, state: ProjectState) -> str:
        lines = ["# 创新点候选清单", ""]
        for idx, item in enumerate(state.innovation_candidates, start=1):
            lines.extend(
                [
                    f"## 候选 {idx}",
                    f"- 方案：{item.claim}",
                    f"- 创新性说明：{item.novelty_reason}",
                    f"- 可行性评分：{item.feasibility_score}",
                    f"- 风险：{item.risk}",
                    f"- 验证计划：{item.verification_plan}",
                    "",
                ]
            )
        return "\n".join(lines)

    def _experiment_plan_text(self, state: ProjectState) -> str:
        plan = state.experiment_plan
        if not plan:
            return "实验计划尚未生成。"
        return "\n".join(
            [
                "# 实验设计书",
                f"数据集：{', '.join(plan.dataset)}",
                f"基线：{', '.join(plan.baselines)}",
                f"指标：{', '.join(plan.metrics)}",
                f"消融：{', '.join(plan.ablations)}",
                f"环境：{', '.join(plan.environment)}",
                "步骤：",
                *[f"- {step}" for step in plan.steps],
                "预期输出：",
                *[f"- {item}" for item in plan.expected_outputs],
            ]
        )

    def _thesis_text(self, state: ProjectState) -> str:
        manifest = state.template_manifest or TemplateManifest([], {}, [], [], [], "", {}, {})
        parts = [
            "# 毕业论文",
            f"模板来源：{state.template_source.template_name if state.template_source else '未设置'}",
            f"模板章节顺序：{' / '.join(manifest.section_mapping)}",
            "",
        ]
        for section in state.paper_outline:
            parts.append(f"## {section}")
            parts.append(state.paper_sections.get(section, ""))
            parts.append("")
        return "\n".join(parts)

    def _ppt_text(self, state: ProjectState) -> str:
        lines = ["答辩 PPT 结构", ""]
        for idx, slide in enumerate(state.ppt_outline, start=1):
            lines.append(f"{idx}. {slide}")
        return "\n".join(lines)

    def _write_text(self, path: Path, content: str) -> str:
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _write_docx_like(self, path: Path, content: str) -> str:
        try:
            from docx import Document  # type: ignore

            document = Document()
            for line in content.splitlines():
                if line.startswith("# "):
                    document.add_heading(line[2:], level=1)
                elif line.startswith("## "):
                    document.add_heading(line[3:], level=2)
                else:
                    document.add_paragraph(line)
            document.save(path)
            return str(path)
        except Exception:
            fallback = path.with_suffix(".md")
            fallback.write_text(content, encoding="utf-8")
            return str(fallback)

    def _write_minimal_pdf(self, path: Path, content: str) -> str:
        wrapped = textwrap.wrap(
            content[:1800].replace("(", "[").replace(")", "]"),
            width=80,
        ) or ["thesis assistant"]
        text_commands = " T* ".join([f"({line}) Tj" for line in wrapped[:25]])
        stream = f"BT /F1 12 Tf 50 780 Td 14 TL {text_commands} ET"
        pdf = (
            "%PDF-1.4\n"
            "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
            "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
            "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
            f"4 0 obj<< /Length {len(stream)} >>stream\n{stream}\nendstream endobj\n"
            "5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
            "xref\n0 6\n0000000000 65535 f \n"
            "0000000010 00000 n \n0000000063 00000 n \n0000000122 00000 n \n0000000250 00000 n \n0000000000 00000 n \n"
            "trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF"
        )
        path.write_bytes(pdf.encode("latin-1", errors="ignore"))
        return str(path)

    def _write_code_zip(self, path: Path, state: ProjectState) -> str:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative_path, content in state.generated_code_files.items():
                archive.writestr(relative_path, content)
        return str(path)

    def _write_pptx_like(self, path: Path, content: str) -> str:
        try:
            from pptx import Presentation  # type: ignore

            presentation = Presentation()
            for slide_text in _split_slides(content):
                slide = presentation.slides.add_slide(presentation.slide_layouts[1])
                slide.shapes.title.text = slide_text["title"]
                slide.placeholders[1].text = slide_text["body"]
            presentation.save(path)
            return str(path)
        except Exception:
            fallback = path.with_suffix(".md")
            fallback.write_text(content, encoding="utf-8")
            return str(fallback)


def _split_slides(content: str) -> list[dict[str, str]]:
    slides: list[dict[str, str]] = []
    current_title = "答辩概览"
    current_lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^\d+\.\s+(.*)$", line)
        if match:
            if current_lines:
                slides.append({"title": current_title, "body": "\n".join(current_lines)})
            current_title = match.group(1)
            current_lines = [f"{current_title} 的关键内容概览。"]
        else:
            current_lines.append(line)
    if current_lines:
        slides.append({"title": current_title, "body": "\n".join(current_lines)})
    return slides or [{"title": "答辩概览", "body": content}]
