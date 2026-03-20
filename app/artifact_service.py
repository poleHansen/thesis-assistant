from __future__ import annotations

import csv
import json
import re
import textwrap
import zipfile
from pathlib import Path

from app.domain import ArtifactBundle, ProjectState, TemplateManifest
from app.storage import ProjectStorage


DOCX_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([\w\-.\u4e00-\u9fff]+)\s*\}\}")


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

        word_template_path = state.template_source.template_path if state.template_source else None
        ppt_template_path = self._resolve_ppt_template_path(state)

        state.artifacts = ArtifactBundle(
            literature_review=self._write_literature_review(reports_dir, state),
            innovation_report=self._write_text(
                reports_dir / "innovation_report.md",
                self._innovation_report(state),
            ),
            experiment_plan=self._write_docx_like(
                reports_dir / "experiment_plan.docx",
                self._experiment_plan_text(state),
                manifest=state.template_manifest,
            ),
            procedure=self._write_docx_like(
                reports_dir / "procedure.docx",
                str(state.result_schema.get("procedure_document", "")),
                manifest=state.template_manifest,
            ),
            thesis_docx=self._write_docx_like(
                reports_dir / "thesis.docx",
                self._thesis_text(state),
                template_path=word_template_path,
                manifest=state.template_manifest,
                placeholder_values=self._thesis_placeholder_values(state),
            ),
            thesis_pdf=self._write_minimal_pdf(
                reports_dir / "thesis.pdf",
                self._thesis_text(state),
            ),
            code_zip=self._write_code_zip(code_dir / "code_bundle.zip", state),
            defense_pptx=self._write_pptx_like(
                slides_dir / "defense.pptx",
                self._ppt_text(state),
                template_path=ppt_template_path,
                manifest=state.template_manifest,
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

    def _resolve_ppt_template_path(self, state: ProjectState) -> str | None:
        uploaded_path = state.result_schema.get("ppt_template_path")
        if isinstance(uploaded_path, str) and uploaded_path.strip():
            return uploaded_path
        if state.template_source and state.template_source.ppt_template_path:
            return state.template_source.ppt_template_path
        return None

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
                "source",
                "doi_or_url",
                "evidence_source",
                "confidence",
                "evidence_quote",
                "pdf_path",
                "pdf_parse_status",
                "pdf_parse_message",
                "citation_count",
                "is_fallback",
                "needs_review",
                "review_note",
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
                "source",
                "doi_or_url",
                "evidence_source",
                "confidence",
                "evidence_quote",
                "pdf_path",
                "pdf_parse_status",
                "pdf_parse_message",
                "citation_count",
                "is_fallback",
                "needs_review",
                "review_note",
            ]
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerows(state.survey_table)
            return str(path)

    def _innovation_report(self, state: ProjectState) -> str:
        selected = state.selected_innovation
        summary = state.result_schema.get("gap_analysis", {}) if isinstance(state.result_schema, dict) else {}
        recommendation = (
            state.result_schema.get("innovation_recommendation", {}) if isinstance(state.result_schema, dict) else {}
        )
        mode = (
            summary.get("mode", selected.evidence_mode if selected else "fallback")
            if isinstance(summary, dict)
            else "fallback"
        )
        common_methods = "、".join(summary.get("common_methods", [])[:3]) if isinstance(summary, dict) else ""
        common_datasets = "、".join(summary.get("common_datasets", [])[:3]) if isinstance(summary, dict) else ""
        common_metrics = "、".join(summary.get("common_metrics", [])[:3]) if isinstance(summary, dict) else ""
        common_limitations = "、".join(summary.get("common_limitations", [])[:3]) if isinstance(summary, dict) else ""
        rare_methods = "、".join(summary.get("rare_methods", [])[:3]) if isinstance(summary, dict) else ""
        rare_datasets = "、".join(summary.get("rare_datasets", [])[:3]) if isinstance(summary, dict) else ""
        rare_metrics = "、".join(summary.get("rare_metrics", [])[:3]) if isinstance(summary, dict) else ""
        gap_overview = str(state.result_schema.get("gap_analysis_overview", "")).strip()
        selected_reason = recommendation.get("selected_reason", selected.recommendation_reason if selected else "")
        lines = [
            "# 创新点分析报告",
            "",
            "## 总体结论",
            f"- 分析模式：{mode}",
            f"- 候选数量：{len(state.innovation_candidates)}",
            f"- 推荐方案：{selected.claim if selected else '尚未生成'}",
            f"- 推荐理由：{selected_reason or '待生成'}",
            f"- 主流方法共性：{common_methods or '待补充'}",
            f"- 主流数据共性：{common_datasets or '待补充'}",
            f"- 主流评测共性：{common_metrics or '待补充'}",
            f"- 常见局限：{common_limitations or '待补充'}",
            f"- 罕见方法线索：{rare_methods or '待补充'}",
            f"- 罕见数据线索：{rare_datasets or '待补充'}",
            f"- 罕见评测线索：{rare_metrics or '待补充'}",
            f"- 最明显 gap：{gap_overview or '待补充'}",
            (
                "- 审核提示：当前结果含 fallback 占位推荐，建议补充文献后再确认最终创新点。"
                if mode == "fallback" or any(item.evidence_mode == "fallback" for item in state.innovation_candidates)
                else "- 审核提示：当前候选主要基于真实结构化文献差异分析生成。"
            ),
            "",
        ]
        if isinstance(summary, dict):
            lines.extend([
                "## 差异分析摘要",
                f"- 方法 gap：{self._format_gap_summary_entries(summary.get('method_gaps', []))}",
                f"- 数据 gap：{self._format_gap_summary_entries(summary.get('data_gaps', []))}",
                f"- 场景 gap：{self._format_gap_summary_entries(summary.get('scenario_gaps', []))}",
                f"- 评价 gap：{self._format_gap_summary_entries(summary.get('evaluation_gaps', []))}",
                f"- 支撑证据映射：{self._format_evidence_map(summary.get('support_evidence_map', {}))}",
                f"- 对照证据映射：{self._format_evidence_map(summary.get('contrast_evidence_map', {}))}",
                "",
            ])
        for idx, item in enumerate(state.innovation_candidates, start=1):
            analysis_basis = "；".join(item.analysis_basis) or "无"
            supporting_evidence = "；".join(item.supporting_evidence) or "无"
            contrast_evidence = "；".join(item.contrast_evidence) or "无"
            lines.extend(
                [
                    f"## 候选 {idx}",
                    f"- 创新点描述：{item.claim}",
                    f"- gap 类型：{item.gap_type}",
                    f"- 支撑文献：{'；'.join(item.supporting_papers) or '无'}",
                    f"- 对照文献：{'；'.join(item.contrast_papers) or '无'}",
                    f"- 分析依据：{analysis_basis}",
                    f"- 支撑证据：{supporting_evidence}",
                    f"- 对照依据：{contrast_evidence}",
                    f"- 创新性说明：{item.novelty_reason}",
                    f"- 少见原因：{item.rare_reason}",
                    f"- 推荐理由：{item.recommendation_reason or '待排序阶段生成'}",
                    f"- 当前名次说明：第 {idx} 名，依据综合评分、证据强度与本科适配度排序。",
                    f"- 证据链解释：优先展示结构化文献中的 limitations / metrics / dataset / problem 摘要，以说明为何判断为该 gap。",
                    (
                        f"- 多维评分：overall={item.overall_score:.2f} / novelty={item.novelty_score:.1f} / "
                        f"feasibility={item.feasibility_score:.1f} / risk={item.risk_score:.1f} / "
                        f"cost={item.experiment_cost:.1f} / undergrad_fit={item.undergrad_fit:.1f} / "
                        f"evidence={item.evidence_strength:.1f}"
                    ),
                    f"- 风险：{item.risk}",
                    f"- 验证计划：{item.verification_plan}",
                    f"- 证据模式：{item.evidence_mode}",
                    (
                        "- 复核建议：该候选为 fallback 占位推荐，进入实验设计前应先补充更多结构化文献证据。"
                        if item.evidence_mode == "fallback"
                        else "- 复核建议：该候选已具备 real 证据，可直接进入实验设计并继续补强实验细节。"
                    ),
                    "",
                ]
            )
        return "\n".join(lines)

    def _format_gap_summary_entries(self, entries: object) -> str:
        if not isinstance(entries, list):
            return "待补充"
        fragments: list[str] = []
        for entry in entries[:2]:
            if not isinstance(entry, dict):
                continue
            focus = str(entry.get("focus", "待补充")).strip() or "待补充"
            description = str(entry.get("description", "")).strip()
            basis = "；".join(str(item) for item in entry.get("basis", [])[:2]) if isinstance(entry.get("basis"), list) else ""
            fragment = f"{focus}：{description}" if description else focus
            if basis:
                fragment = f"{fragment}（依据：{basis}）"
            fragments.append(fragment)
        return "；".join(fragments) or "待补充"

    def _format_evidence_map(self, mapping: object) -> str:
        if not isinstance(mapping, dict):
            return "待补充"
        chunks: list[str] = []
        for label, entries in mapping.items():
            if not isinstance(entries, list) or not entries:
                continue
            first = entries[0]
            if not isinstance(first, dict):
                continue
            phrase = str(first.get("phrase", "待补充")).strip() or "待补充"
            papers = "、".join(first.get("supporting_papers", [])[:2]) if isinstance(first.get("supporting_papers"), list) else ""
            chunks.append(f"{label}={phrase}{f'（{papers}）' if papers else ''}")
        return "；".join(chunks) or "待补充"

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
        template_name = state.template_source.template_name if state.template_source else "未设置"
        parts = [
            "# 毕业论文",
            f"模板来源：{template_name}",
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

    def _write_docx_like(
        self,
        path: Path,
        content: str,
        *,
        template_path: str | None = None,
        manifest: TemplateManifest | None = None,
        placeholder_values: dict[str, str] | None = None,
    ) -> str:
        try:
            from docx import Document  # type: ignore

            document = self._load_docx_document(Document, template_path)
            if placeholder_values and self._replace_docx_placeholders(document, placeholder_values):
                document.save(path)
                return str(path)
            for line in content.splitlines():
                self._append_docx_line(document, line, manifest)
            document.save(path)
            return str(path)
        except Exception:
            fallback = path.with_suffix(".md")
            fallback.write_text(content, encoding="utf-8")
            return str(fallback)

    def _load_docx_document(self, document_cls, template_path: str | None):
        if template_path:
            candidate = Path(template_path)
            if candidate.exists():
                try:
                    return document_cls(str(candidate))
                except Exception:
                    pass
        return document_cls()

    def _thesis_placeholder_values(self, state: ProjectState) -> dict[str, str]:
        manifest = state.template_manifest or TemplateManifest([], {}, [], [], [], "", {}, {})
        template_name = state.template_source.template_name if state.template_source else "未设置"
        values: dict[str, str] = {
            "cover.题目": state.request.topic,
            "thesis.title": state.request.topic,
            "thesis.template_name": template_name,
        }
        for field_name in manifest.cover_fields:
            values.setdefault(f"cover.{field_name}", "")
        section_names = list(dict.fromkeys([*manifest.section_mapping, *state.paper_outline, *state.paper_sections.keys()]))
        for section in section_names:
            values[f"section.{section}"] = state.paper_sections.get(section, "")
        return values

    def _replace_docx_placeholders(self, document, placeholder_values: dict[str, str]) -> int:
        replaced = 0
        for paragraph in list(document.paragraphs):
            replaced += self._replace_docx_placeholders_in_paragraph(paragraph, placeholder_values)
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in list(cell.paragraphs):
                        replaced += self._replace_docx_placeholders_in_paragraph(paragraph, placeholder_values)
        return replaced

    def _replace_docx_placeholders_in_paragraph(self, paragraph, placeholder_values: dict[str, str]) -> int:
        original = paragraph.text
        if not original or "{{" not in original or "}}" not in original:
            return 0

        replaced_count = 0

        def replace_match(match: re.Match[str]) -> str:
            nonlocal replaced_count
            key = match.group(1)
            if key not in placeholder_values:
                return match.group(0)
            replaced_count += 1
            return placeholder_values[key]

        updated = DOCX_PLACEHOLDER_PATTERN.sub(replace_match, original)
        if replaced_count:
            paragraph.text = updated
        return replaced_count

    def _append_docx_line(self, document, line: str, manifest: TemplateManifest | None) -> None:
        if line.startswith("# "):
            style_name = self._resolve_docx_style(
                document,
                [
                    self._manifest_style(manifest, "title"),
                    "Title",
                    self._manifest_style(manifest, "chapter"),
                    "Heading 1",
                ],
            )
            self._add_docx_paragraph(document, line[2:], style_name, heading_level=1)
            return

        if line.startswith("## "):
            style_name = self._resolve_docx_style(
                document,
                [
                    self._manifest_style(manifest, "chapter"),
                    "Heading 1",
                    self._manifest_style(manifest, "section"),
                    "Heading 2",
                ],
            )
            self._add_docx_paragraph(document, line[3:], style_name, heading_level=2)
            return

        style_name = self._resolve_docx_style(
            document,
            [self._manifest_style(manifest, "body"), "Normal"],
        )
        self._add_docx_paragraph(document, line, style_name)

    def _manifest_style(self, manifest: TemplateManifest | None, key: str) -> str | None:
        if not manifest:
            return None
        return manifest.style_mapping.get(key)

    def _resolve_docx_style(self, document, candidates: list[str | None]) -> str | None:
        available = {style.name for style in document.styles}
        for candidate in candidates:
            if candidate and candidate in available:
                return candidate
        return None

    def _add_docx_paragraph(
        self,
        document,
        text: str,
        style_name: str | None,
        *,
        heading_level: int | None = None,
    ) -> None:
        if style_name:
            document.add_paragraph(text, style=style_name)
            return
        if heading_level is not None:
            document.add_heading(text, level=heading_level)
            return
        document.add_paragraph(text)

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

    def _write_pptx_like(
        self,
        path: Path,
        content: str,
        *,
        template_path: str | None = None,
        manifest: TemplateManifest | None = None,
    ) -> str:
        try:
            from pptx import Presentation  # type: ignore
            from pptx.util import Inches  # type: ignore

            presentation = self._load_presentation(Presentation, template_path)
            slides = _split_slides(content, manifest.ppt_layouts if manifest else [])
            for slide_text in slides:
                slide_layout = self._choose_slide_layout(presentation, slide_text["layout_hint"])
                slide = presentation.slides.add_slide(slide_layout)
                if slide.shapes.title is not None:
                    slide.shapes.title.text = slide_text["title"]
                body_placeholder = self._find_body_placeholder(slide)
                if body_placeholder is not None:
                    body_placeholder.text = slide_text["body"]
                else:
                    text_box = slide.shapes.add_textbox(
                        Inches(1.0),
                        Inches(1.8),
                        Inches(8.0),
                        Inches(4.5),
                    )
                    text_box.text_frame.text = slide_text["body"]
            presentation.save(path)
            return str(path)
        except Exception:
            fallback = path.with_suffix(".md")
            fallback.write_text(content, encoding="utf-8")
            return str(fallback)

    def _load_presentation(self, presentation_cls, template_path: str | None):
        if template_path:
            candidate = Path(template_path)
            if candidate.exists():
                try:
                    return presentation_cls(str(candidate))
                except Exception:
                    pass
        return presentation_cls()

    def _choose_slide_layout(self, presentation, layout_hint: str):
        normalized_hint = layout_hint.strip().lower()
        if normalized_hint:
            for layout in presentation.slide_layouts:
                layout_name = getattr(layout, "name", "") or ""
                if normalized_hint in layout_name.lower() or layout_name.lower() in normalized_hint:
                    return layout
        if len(presentation.slide_layouts) > 1:
            return presentation.slide_layouts[1]
        return presentation.slide_layouts[0]

    def _find_body_placeholder(self, slide):
        title = slide.shapes.title
        for shape in slide.placeholders:
            if shape is title:
                continue
            if hasattr(shape, "text_frame"):
                return shape
        return None


def _split_slides(content: str, layout_hints: list[str]) -> list[dict[str, str]]:
    slides: list[dict[str, str]] = []
    current_title = "答辩概览"
    current_lines: list[str] = []
    slide_index = 0
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^\d+\.\s+(.*)$", line)
        if match:
            if current_lines:
                slides.append(
                    {
                        "title": current_title,
                        "body": "\n".join(current_lines),
                        "layout_hint": _resolve_layout_hint(layout_hints, slide_index),
                    }
                )
                slide_index += 1
            current_title = match.group(1)
            current_lines = [f"{current_title} 的关键信息概览。"]
        else:
            current_lines.append(line)
    if current_lines:
        slides.append(
            {
                "title": current_title,
                "body": "\n".join(current_lines),
                "layout_hint": _resolve_layout_hint(layout_hints, slide_index),
            }
        )
    return slides or [{"title": "答辩概览", "body": content, "layout_hint": ""}]


def _resolve_layout_hint(layout_hints: list[str], index: int) -> str:
    if not layout_hints:
        return ""
    if index < len(layout_hints):
        return layout_hints[index]
    return layout_hints[-1]
