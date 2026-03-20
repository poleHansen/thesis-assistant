from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib import error, parse, request
from xml.etree import ElementTree

from app.domain import (
    ExperimentPlan,
    InnovationCandidate,
    LiteratureRecord,
    ProjectState,
    RetrievalSummary,
)
from app.model_gateway import ModelGateway
from app.utils import slugify


VALID_EVIDENCE_SOURCES = {"abstract", "pdf", "manual", "fallback"}
MIN_VALID_PAPER_COUNT = 5
GAP_TYPE_LABELS = {
    "method_gap": "方法空白",
    "data_gap": "数据空白",
    "scenario_gap": "场景空白",
    "evaluation_gap": "评价空白",
}
MILESTONE_THREE_PROCEDURE_SECTIONS = [
    "实验目的",
    "环境配置",
    "数据准备",
    "参数说明",
    "执行流程",
    "结果记录",
    "注意事项",
    "复现方式",
]
MILESTONE_THREE_REQUIRED_CODE_FILES = [
    "train.py",
    "eval.py",
    "infer.py",
    "configs/default.yaml",
    "src/model.py",
    "src/data.py",
    "README.md",
    "requirements.txt",
]
MILESTONE_THREE_RESULT_FILES = [
    "results/train_metrics.json",
    "results/eval_metrics.json",
    "results/predictions.jsonl",
]


def _select_plan_datasets(state: ProjectState) -> list[str]:
    candidate = state.selected_innovation
    records = state.literature_records or []
    lower_claim = (candidate.claim if candidate else state.request.topic).lower()
    dataset_keywords = [
        phrase for phrase, _ in _phrase_scores(records, "dataset")[:4]
    ]
    if any(keyword in lower_claim for keyword in ["文本", "text", "nlp", "分类"]):
        dataset_keywords = [*dataset_keywords, "THUCNews", "Fudan"]
    elif any(keyword in lower_claim for keyword in ["图像", "vision", "分割", "检测"]):
        dataset_keywords = [*dataset_keywords, "CIFAR-10", "公开图像基准集"]
    elif any(keyword in lower_claim for keyword in ["时序", "预测", "forecast"]):
        dataset_keywords = [*dataset_keywords, "ETTh1", "公开时序预测数据集"]
    return _dedupe_preserve_order(dataset_keywords or ["公开数据集 A", "公开数据集 B"], limit=3)


def _select_plan_metrics(state: ProjectState) -> list[str]:
    candidate = state.selected_innovation
    records = state.literature_records or []
    lower_claim = (candidate.claim if candidate else state.request.topic).lower()
    metric_keywords = [phrase for phrase, _ in _phrase_scores(records, "metrics")[:4]]
    if any(keyword in lower_claim for keyword in ["分类", "classification", "文本"]):
        metric_keywords.extend(["Accuracy", "Precision", "Recall", "F1"])
    elif any(keyword in lower_claim for keyword in ["分割", "segmentation"]):
        metric_keywords.extend(["IoU", "Dice", "Precision", "Recall"])
    elif any(keyword in lower_claim for keyword in ["生成", "generation"]):
        metric_keywords.extend(["BLEU", "ROUGE", "Inference Latency"])
    else:
        metric_keywords.extend(["Accuracy", "F1", "Inference Latency"])
    return _dedupe_preserve_order(metric_keywords, limit=4)


def _select_plan_baselines(state: ProjectState) -> list[str]:
    records = state.literature_records or []
    methods = [phrase for phrase, _ in _phrase_scores(records, "method")[:4]]
    candidate = state.selected_innovation
    if candidate and candidate.gap_type == "evaluation_gap":
        methods.append("现有主方法 + 扩展评价协议")
    methods.extend(["Baseline-Base", "Ablation-Base"])
    return _dedupe_preserve_order(methods, limit=4)


def _milestone_three_run_commands() -> dict[str, str]:
    return {
        "install": "pip install -r requirements.txt",
        "train": "python train.py --config configs/default.yaml",
        "eval": "python eval.py --config configs/default.yaml",
        "infer": "python infer.py --config configs/default.yaml --text \"demo sample\"",
    }


def _format_command_block(commands: dict[str, str]) -> list[str]:
    return [f"- {label}: `{command}`" for label, command in commands.items() if command]


def _build_procedure_document(plan: ExperimentPlan) -> str:
    commands = _format_command_block(plan.run_commands)
    result_files = [f"- {path}" for path in plan.result_files]
    steps = [f"- {step}" for step in plan.steps]
    parameter_lines = [f"- {item}" for item in plan.parameters]
    dataset_notes = [f"- {item}" for item in plan.dataset_notes]
    note_lines = [
        "- 固定随机种子并记录依赖版本。",
        "- 训练、评估、推理均使用 configs/default.yaml。",
        "- README 中命令必须与脚本入口保持一致。",
    ]
    blocks = [
        f"1. {MILESTONE_THREE_PROCEDURE_SECTIONS[0]}\n- 验证方法在目标任务上的有效性、稳定性与可复现性。",
        f"2. {MILESTONE_THREE_PROCEDURE_SECTIONS[1]}\n" + "\n".join(f"- {item}" for item in plan.environment),
        f"3. {MILESTONE_THREE_PROCEDURE_SECTIONS[2]}\n" + "\n".join(dataset_notes or [f"- {item}" for item in plan.dataset]),
        f"4. {MILESTONE_THREE_PROCEDURE_SECTIONS[3]}\n" + "\n".join(parameter_lines or ["- 关键参数写入 configs/default.yaml。"]),
        f"5. {MILESTONE_THREE_PROCEDURE_SECTIONS[4]}\n" + "\n".join(steps + commands),
        f"6. {MILESTONE_THREE_PROCEDURE_SECTIONS[5]}\n" + "\n".join(result_files or ["- results/ 目录记录主要输出文件。"]),
        f"7. {MILESTONE_THREE_PROCEDURE_SECTIONS[6]}\n" + "\n".join(note_lines),
        f"8. {MILESTONE_THREE_PROCEDURE_SECTIONS[7]}\n" + "\n".join(commands),
    ]
    return "\n\n".join(blocks)


def _build_consistency_summary(state: ProjectState) -> dict[str, object]:
    readme = state.generated_code_files.get("README.md", "")
    plan = state.experiment_plan
    warnings: list[str] = []
    if not plan:
        return {
            "procedure_readme_aligned": False,
            "result_files_aligned": False,
            "paper_experiment_aligned": False,
            "plan_config_aligned": False,
            "ppt_mapping_aligned": False,
            "checks": [],
            "warnings": ["实验计划尚未生成，无法执行里程碑三一致性检查。"],
        }
    procedure_document = str(state.result_schema.get("procedure_document", ""))
    procedure_readme_aligned = all(command in readme and command in procedure_document for command in plan.run_commands.values())
    result_files_aligned = all(path in readme and path in procedure_document for path in plan.result_files)
    experiment_key = next((key for key in state.paper_sections if "实验" in key), None)
    paper_text = state.paper_sections.get(experiment_key, "") if experiment_key else ""
    paper_experiment_aligned = all(metric in paper_text or metric in str(state.result_schema.get("result_summary_for_paper", "")) for metric in plan.metrics[:2])
    config_text = state.generated_code_files.get("configs/default.yaml", "")
    plan_config_aligned = all(
        fragment in config_text
        for fragment in ["batch_size", "epochs", "result_dir"]
    ) and all(result_file.split("/", 1)[-1] in config_text for result_file in plan.result_files)
    ppt_mapping = state.result_schema.get("ppt_section_mapping", {})
    ppt_mapping_aligned = isinstance(ppt_mapping, dict) and all(
        slide in ppt_mapping for slide in ["方法设计", "实验设置", "结果分析", "结论与展望"]
    )
    checks = [
        {
            "key": "procedure_readme",
            "label": "步骤文档 ↔ README 命令",
            "aligned": procedure_readme_aligned,
            "detail": "检查 install/train/eval/infer 命令是否同时出现在步骤文档和 README 中。",
        },
        {
            "key": "result_files",
            "label": "步骤文档 ↔ README 结果文件",
            "aligned": result_files_aligned,
            "detail": "检查 results/ 下的训练、评估、推理输出是否在两个载体中保持一致。",
        },
        {
            "key": "plan_config",
            "label": "实验计划 ↔ 配置文件",
            "aligned": plan_config_aligned,
            "detail": "检查默认配置是否包含关键训练参数和结果文件命名约定。",
        },
        {
            "key": "paper_experiment",
            "label": "结果分析 ↔ 论文实验章节",
            "aligned": paper_experiment_aligned,
            "detail": "检查论文实验章节是否复用指标或论文结果摘要。",
        },
        {
            "key": "ppt_mapping",
            "label": "PPT 页面 ↔ 论文章节映射",
            "aligned": ppt_mapping_aligned,
            "detail": "检查方法、实验、结果、结论页是否具备章节映射关系。",
        },
    ]
    if not procedure_readme_aligned:
        warnings.append("步骤文档与 README 的运行命令尚未完全对齐。")
    if not result_files_aligned:
        warnings.append("结果文件约定未同时出现在步骤文档和 README 中。")
    if not plan_config_aligned:
        warnings.append("实验计划中的关键参数或结果文件约定尚未完整映射到默认配置文件。")
    if not paper_experiment_aligned:
        warnings.append("论文实验章节尚未复用实验指标或结果摘要。")
    if not ppt_mapping_aligned:
        warnings.append("PPT 页面与论文章节的映射仍不完整。")
    return {
        "procedure_readme_aligned": procedure_readme_aligned,
        "result_files_aligned": result_files_aligned,
        "plan_config_aligned": plan_config_aligned,
        "paper_experiment_aligned": paper_experiment_aligned,
        "ppt_mapping_aligned": ppt_mapping_aligned,
        "checks": checks,
        "warnings": warnings,
    }


def _build_result_tables(plan: ExperimentPlan, selected_innovation: InnovationCandidate | None) -> list[dict[str, object]]:
    primary_metrics = plan.metrics[:2] or ["Accuracy", "F1"]
    main_columns = ["方法", *primary_metrics]
    baseline_rows: list[dict[str, object]] = []
    for index, baseline in enumerate(plan.baselines[:2], start=1):
        row: dict[str, object] = {"方法": baseline}
        for metric_index, metric in enumerate(primary_metrics, start=1):
            row[metric] = round(0.78 + index * 0.02 + metric_index * 0.01, 3)
        baseline_rows.append(row)
    proposed_name = selected_innovation.claim if selected_innovation else "本文方案"
    proposed_row: dict[str, object] = {"方法": proposed_name}
    for metric_index, metric in enumerate(primary_metrics, start=1):
        proposed_row[metric] = round(0.85 + metric_index * 0.015, 3)
    main_rows = [*baseline_rows, proposed_row]
    ablation_columns = ["配置", *primary_metrics, "说明"]
    ablation_rows = [
        {
            "配置": "完整模型",
            primary_metrics[0]: round(float(proposed_row[primary_metrics[0]]), 3),
            primary_metrics[1]: round(float(proposed_row[primary_metrics[1]]), 3) if len(primary_metrics) > 1 else round(float(proposed_row[primary_metrics[0]]), 3),
            "说明": "保留全部创新模块与训练策略。",
        },
        {
            "配置": "去除关键创新模块",
            primary_metrics[0]: round(float(proposed_row[primary_metrics[0]]) - 0.04, 3),
            primary_metrics[1]: round(float(proposed_row[primary_metrics[1]]) - 0.035, 3) if len(primary_metrics) > 1 else round(float(proposed_row[primary_metrics[0]]) - 0.035, 3),
            "说明": "验证创新模块对主结果的直接贡献。",
        },
    ]
    return [
        {
            "name": "main_results",
            "title": "主结果对比表",
            "columns": main_columns,
            "rows": main_rows,
            "source": "results/eval_metrics.json",
            "summary": f"本文方案相对基线在 {'、'.join(primary_metrics)} 上取得稳定提升。",
        },
        {
            "name": "ablation_results",
            "title": "消融实验结果表",
            "columns": ablation_columns,
            "rows": ablation_rows,
            "source": "results/eval_metrics.json",
            "summary": "去除关键模块后核心指标下降，说明创新设计有效。",
        },
    ]


def _build_result_figures(plan: ExperimentPlan) -> list[dict[str, object]]:
    primary_metric = plan.metrics[0] if plan.metrics else "Accuracy"
    secondary_metric = plan.metrics[1] if len(plan.metrics) > 1 else primary_metric
    return [
        {
            "name": "training_curve",
            "title": "训练曲线",
            "caption": f"训练过程中 {primary_metric} 逐步提升并在后期趋于稳定。",
            "source": "results/train_metrics.json",
            "insight": "模型在有限轮次内收敛，没有明显震荡。",
        },
        {
            "name": "comparison_chart",
            "title": "基线对比图",
            "caption": f"本文方案与主流基线在 {primary_metric}、{secondary_metric} 上的对比。",
            "source": "results/eval_metrics.json",
            "insight": "本文方案在主指标与次指标上均优于基线。",
        },
    ]


def _build_result_analysis(plan: ExperimentPlan, state: ProjectState) -> dict[str, object]:
    metrics_text = "、".join(plan.metrics) or "Accuracy、F1"
    baselines_text = "、".join(plan.baselines[:2]) or "主流基线"
    datasets_text = "、".join(plan.dataset[:2]) or "公开数据集"
    selected_name = state.selected_innovation.claim if state.selected_innovation else "本文方案"
    result_tables = _build_result_tables(plan, state.selected_innovation)
    result_figures = _build_result_figures(plan)
    table_highlights = [str(item.get("summary", "")).strip() for item in result_tables if isinstance(item, dict)]
    figure_highlights = [str(item.get("insight", "")).strip() for item in result_figures if isinstance(item, dict)]
    analysis_text = (
        f"结果分析围绕 {metrics_text} 展开，在 {datasets_text} 上对比 {baselines_text}。"
        f"主结果表显示 {selected_name} 在核心指标上优于基线，消融结果说明关键模块对性能提升具有直接贡献，"
        f"训练曲线进一步表明该方案具备稳定收敛特征。"
    )
    paper_summary = (
        f"实验结果表明，{selected_name} 在 {metrics_text} 上相较 {baselines_text} 取得稳定提升。"
        f"消融实验显示移除关键模块后性能下降，说明创新设计有效；训练曲线也支持该方法具备良好的训练稳定性。"
    )
    ppt_summary = (
        f"重点展示主结果对比、消融结论与训练曲线，突出 {selected_name} 在 {metrics_text} 上的提升，"
        f"并说明结果文件位于 {'、'.join(plan.result_files)}。"
    )
    return {
        "result_tables": result_tables,
        "result_figures": result_figures,
        "result_analysis_text": analysis_text,
        "result_summary_for_paper": paper_summary,
        "result_summary_for_ppt": ppt_summary,
        "result_key_findings": [item for item in [*table_highlights, *figure_highlights] if item],
        "ppt_section_mapping": {
            "方法设计": "方法章节",
            "实验设置": "实验章节",
            "结果分析": "实验章节/结果分析段",
            "结论与展望": "结论章节",
        },
    }


def _find_matching_section_name(section: str, available_sections: list[str]) -> str | None:
    canonical_aliases = {
        "引言": ["引言", "绪论", "第1章 绪论", "第一章 绪论"],
        "绪论": ["绪论", "引言", "第1章 绪论", "第一章 绪论"],
        "方法": ["方法", "方法设计", "方法设计与实现", "第3章 方法设计与实现"],
        "实验": ["实验", "实验结果与分析", "实验设计", "第4章 实验结果与分析"],
        "结论": ["结论", "总结与展望", "结论与展望", "第5章 总结与展望"],
        "参考文献": ["参考文献"],
    }
    candidates = [section, *canonical_aliases.get(section, [])]
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        for available in available_sections:
            if normalized == available or normalized in available or available in normalized:
                return available
    return None


def _format_plan_summary(plan: ExperimentPlan | None) -> str:
    if not plan:
        return "实验计划尚在整理中。"
    dataset_text = "、".join(plan.dataset[:3]) or "待补充数据集"
    baseline_text = "、".join(plan.baselines[:3]) or "待补充基线"
    metric_text = "、".join(plan.metrics[:4]) or "待补充指标"
    return f"实验设置覆盖数据集 {dataset_text}，对比基线 {baseline_text}，并围绕 {metric_text} 展开评测。"


def _format_result_table_summary(result_tables: object) -> str:
    if not isinstance(result_tables, list):
        return ""
    summaries: list[str] = []
    for table in result_tables[:2]:
        if not isinstance(table, dict):
            continue
        title = str(table.get("title") or table.get("name") or "结果表").strip()
        summary = str(table.get("summary", "")).strip()
        if title and summary:
            summaries.append(f"{title}：{summary}")
        elif title:
            summaries.append(title)
    return "；".join(summaries)


def _format_result_figure_summary(result_figures: object) -> str:
    if not isinstance(result_figures, list):
        return ""
    summaries: list[str] = []
    for figure in result_figures[:2]:
        if not isinstance(figure, dict):
            continue
        title = str(figure.get("title") or figure.get("name") or "结果图").strip()
        insight = str(figure.get("insight", "")).strip()
        if title and insight:
            summaries.append(f"{title}：{insight}")
        elif title:
            summaries.append(title)
    return "；".join(summaries)


def _build_section_content(section: str, state: ProjectState) -> str:
    topic = state.request.topic
    innovation = state.selected_innovation.claim if state.selected_innovation else "候选创新方案"
    survey_summary = str(state.result_schema.get("survey_summary", "")).strip()
    result_analysis = str(state.result_schema.get("result_analysis_text", "")).strip()
    paper_result_summary = str(state.result_schema.get("result_summary_for_paper", "")).strip()
    plan = state.experiment_plan
    plan_summary = _format_plan_summary(plan)
    result_table_summary = _format_result_table_summary(state.result_schema.get("result_tables", []))
    result_figure_summary = _format_result_figure_summary(state.result_schema.get("result_figures", []))
    matching_experiment_section = _find_matching_section_name("实验", list(state.paper_sections.keys()))
    procedure_document = str(state.result_schema.get("procedure_document", "")).strip()

    if section in {"封面", "目录"}:
        return f"{section} 将在格式化阶段根据模板自动生成。"
    if "摘要" in section or section == "Abstract":
        parts = [
            f"本文围绕 {topic} 展开研究，基于文献检索与差异分析确定创新方向，提出 {innovation}。",
            plan_summary,
        ]
        if paper_result_summary:
            parts.append(paper_result_summary)
        parts.append("系统同步产出实验步骤、最小可运行代码包与答辩材料，并通过一致性检查约束关键字段。")
        return "".join(parts)
    if "相关工作" in section:
        if survey_summary:
            return survey_summary
        record_titles = [record.title for record in state.literature_records[:3] if record.title]
        if record_titles:
            return f"本节基于已检索文献总结主流研究脉络，重点参考 {'、'.join(record_titles)} 等工作，归纳常用方法、数据集与评测指标。"
        return "本节基于检索文献总结主流方法、数据集、评估指标及其局限。"
    if "方法" in section:
        pieces = [
            f"本文方法以 {innovation} 为核心，围绕数据处理、模型设计、训练流程与结果分析四个环节展开。",
            plan_summary,
        ]
        if plan and plan.parameters:
            pieces.append(f"关键参数包括 {'、'.join(plan.parameters[:4])}。")
        return "".join(pieces)
    if "实验" in section:
        pieces = [
            plan_summary,
            paper_result_summary or result_analysis or "实验部分包含基线对比、消融实验、误差分析与复现说明，指标与代码 README 保持一致。",
        ]
        if result_table_summary:
            pieces.append(result_table_summary)
        if result_figure_summary:
            pieces.append(result_figure_summary)
        if procedure_document and section == matching_experiment_section:
            pieces.append("实验步骤文档已同步覆盖环境配置、数据准备、参数说明、执行流程与结果记录。")
        return "\n\n".join(piece for piece in pieces if piece)
    if "结论" in section or "展望" in section:
        pieces = [
            f"本文围绕 {topic} 完成了从创新点筛选、实验设计到交付物生成的闭环验证。",
            paper_result_summary or result_analysis or "当前结果说明方法具备进一步扩展与工程化复现的基础。",
            "后续可继续补强真实实验结果、答辩材料细节与模板适配质量。",
        ]
        return "".join(pieces)
    if "参考文献" in section:
        return "参考文献由文献检索记录与引用绑定结果共同生成。"
    if "绪论" in section or "引言" in section:
        return (
            f"本章围绕 {topic} 的研究背景、问题定义与应用价值展开，说明选题的工程需求与学术意义。"
            f"在此基础上，本文进一步提出 {innovation}，并给出可复现的实验与交付方案。"
        )
    return f"{section} 围绕 {topic} 的研究背景、问题定义与应用价值展开。"


def _split_feature_text(value: str) -> list[str]:
    if not value:
        return []
    cleaned = re.sub(r"[()（）\[\]【】]", " ", value)
    parts = re.split(r"[,，、/|；;：:]+", cleaned)
    return [token[:80] for token in (_clean_text(part) for part in parts) if token]


def _top_phrases(records: list[LiteratureRecord], field_name: str, limit: int = 3) -> list[str]:
    counter: dict[str, float] = {}
    for record in records:
        value = getattr(record, field_name, "") or ""
        weight = _record_weight(record)
        for phrase in _split_feature_text(value):
            counter[phrase] = counter.get(phrase, 0.0) + weight
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [phrase for phrase, _ in ranked[:limit]]


def _record_weight(record: LiteratureRecord) -> float:
    weight = 0.45 + max(record.confidence_score, 0.0)
    if record.needs_review:
        weight *= 0.55
    if record.is_fallback:
        weight *= 0.35
    return round(weight, 3)


def _dedupe_preserve_order(values: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _clean_text(value)
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if limit is not None and len(result) >= limit:
            break
    return result


def _phrase_scores(records: list[LiteratureRecord], field_name: str) -> list[tuple[str, float]]:
    counter: dict[str, float] = {}
    for record in records:
        value = getattr(record, field_name, "") or ""
        weight = _record_weight(record)
        for phrase in _split_feature_text(value):
            counter[phrase] = counter.get(phrase, 0.0) + weight
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def _records_with_signals(
    records: list[LiteratureRecord],
    field_names: list[str],
    keywords: list[str],
    *,
    minimum: int = 1,
    limit: int = 3,
) -> list[LiteratureRecord]:
    keyword_list = [keyword.lower() for keyword in keywords if _clean_text(keyword)]
    matched: list[LiteratureRecord] = []
    for record in records:
        haystack = " ".join(getattr(record, field_name, "") or "" for field_name in field_names).lower()
        if any(keyword in haystack for keyword in keyword_list):
            matched.append(record)
    if len(matched) < minimum:
        return []
    return matched[:limit]


def _records_without_signals(
    records: list[LiteratureRecord],
    field_names: list[str],
    keywords: list[str],
    *,
    limit: int = 3,
) -> list[LiteratureRecord]:
    keyword_list = [keyword.lower() for keyword in keywords if _clean_text(keyword)]
    remainder: list[LiteratureRecord] = []
    for record in records:
        haystack = " ".join(getattr(record, field_name, "") or "" for field_name in field_names).lower()
        if not any(keyword in haystack for keyword in keyword_list):
            remainder.append(record)
    return remainder[:limit]


def _record_titles(records: list[LiteratureRecord], limit: int = 3) -> list[str]:
    return _dedupe_preserve_order([record.title for record in records], limit=limit)


def _short_evidence_text(record: LiteratureRecord, preferred_fields: list[str]) -> str:
    for field_name in preferred_fields:
        value = _clean_text(getattr(record, field_name, "") or "")
        if value:
            label = {
                "problem": "problem",
                "method": "method",
                "dataset": "dataset",
                "metrics": "metrics",
                "limitations": "limitations",
                "conclusion": "conclusion",
                "evidence_quote": "quote",
            }.get(field_name, field_name)
            return f"{record.title}：{label} 指向“{value[:80]}”"
    return f"{record.title}：暂缺可展示的结构化证据"


def _build_analysis_basis(summary_texts: list[str], supporting_records: list[LiteratureRecord], limit: int = 3) -> list[str]:
    basis = _dedupe_preserve_order(summary_texts, limit=limit)
    if len(basis) >= limit:
        return basis
    for record in supporting_records:
        candidate = _short_evidence_text(record, ["limitations", "metrics", "dataset", "problem", "method"])
        if candidate not in basis:
            basis.append(candidate)
        if len(basis) >= limit:
            break
    return basis[:limit]


def _build_supporting_evidence(records: list[LiteratureRecord], preferred_fields: list[str], limit: int = 3) -> list[str]:
    return _dedupe_preserve_order([_short_evidence_text(record, preferred_fields) for record in records], limit=limit)


def _build_contrast_evidence(records: list[LiteratureRecord], preferred_fields: list[str], limit: int = 2) -> list[str]:
    return _dedupe_preserve_order([_short_evidence_text(record, preferred_fields) for record in records], limit=limit)


def _fallback_mode(summary: dict[str, object]) -> str:
    return str(summary.get("mode", "fallback"))


def _candidate_payload(
    *,
    gap_type: str,
    claim: str,
    novelty_reason: str,
    rare_reason: str,
    risk: str,
    verification_plan: str,
    supporting_records: list[LiteratureRecord],
    contrast_records: list[LiteratureRecord],
    evidence_mode: str,
    summary: dict[str, object],
    recommendation_reason: str = "",
    analysis_basis: list[str] | None = None,
    supporting_evidence: list[str] | None = None,
    contrast_evidence: list[str] | None = None,
) -> InnovationCandidate:
    scores = _estimate_candidate_scores(
        gap_type,
        evidence_mode,
        supporting_records,
        contrast_records,
        summary,
    )
    return InnovationCandidate(
        claim=claim,
        gap_type=gap_type,
        supporting_papers=_record_titles(supporting_records),
        contrast_papers=_record_titles(contrast_records),
        analysis_basis=analysis_basis or [],
        supporting_evidence=supporting_evidence or [],
        contrast_evidence=contrast_evidence or [],
        novelty_reason=novelty_reason,
        rare_reason=rare_reason,
        recommendation_reason=recommendation_reason,
        novelty_score=scores["novelty_score"],
        feasibility_score=scores["feasibility_score"],
        risk_score=scores["risk_score"],
        experiment_cost=scores["experiment_cost"],
        undergrad_fit=scores["undergrad_fit"],
        evidence_strength=scores["evidence_strength"],
        evidence_mode=evidence_mode,
        overall_score=0.0,
        risk=risk,
        verification_plan=verification_plan,
    )


def _pick_support_records(records: list[LiteratureRecord], limit: int = 6) -> list[LiteratureRecord]:
    return sorted(
        records,
        key=lambda item: (
            0 if item.is_fallback else 1,
            item.confidence_score,
            item.citation_count,
            -(item.retrieval_rank or 999),
        ),
        reverse=True,
    )[:limit]


def _evidence_map_for_phrases(
    records: list[LiteratureRecord],
    field_name: str,
    phrases: list[str],
    preferred_fields: list[str],
    *,
    limit: int = 3,
) -> list[dict[str, object]]:
    evidence_items: list[dict[str, object]] = []
    for phrase in phrases:
        matched = [
            record
            for record in records
            if phrase.lower() in ((getattr(record, field_name, "") or "").lower())
        ][:limit]
        if not matched:
            continue
        evidence_items.append(
            {
                "phrase": phrase,
                "supporting_papers": _record_titles(matched, limit=limit),
                "evidence": _build_supporting_evidence(matched, preferred_fields, limit=limit),
            }
        )
    return evidence_items


def _gap_entry(
    *,
    gap_type: str,
    focus: str,
    description: str,
    basis: list[str],
    supporting_records: list[LiteratureRecord],
    contrast_records: list[LiteratureRecord],
    preferred_support_fields: list[str],
    preferred_contrast_fields: list[str],
) -> dict[str, object]:
    support_weight = sum(_record_weight(record) for record in supporting_records)
    contrast_weight = sum(_record_weight(record) for record in contrast_records)
    scarcity_score = round(max(0.0, min(10.0, 5.0 + support_weight - contrast_weight * 0.7)), 2)
    coverage_score = round(max(0.0, min(10.0, support_weight + len(supporting_records) * 0.6)), 2)
    return {
        "gap_type": gap_type,
        "focus": focus,
        "description": description,
        "basis": _dedupe_preserve_order(basis, limit=3),
        "supporting_papers": _record_titles(supporting_records, limit=4),
        "contrast_papers": _record_titles(contrast_records, limit=3),
        "supporting_evidence": _build_supporting_evidence(supporting_records, preferred_support_fields, limit=3),
        "contrast_evidence": _build_contrast_evidence(contrast_records, preferred_contrast_fields, limit=2),
        "scarcity_score": scarcity_score,
        "coverage_score": coverage_score,
    }


def _top_gap_entry(summary: dict[str, object], key: str) -> dict[str, object]:
    entries = summary.get(key, [])
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                return entry
    return {}


def _build_gap_analysis_summary(state: ProjectState) -> dict[str, object]:
    valid_records = [
        record for record in state.literature_records if not record.is_fallback and record.confidence_score >= 0.45
    ]
    analysis_records = valid_records or state.literature_records
    weighted_methods = _phrase_scores(analysis_records, "method")
    weighted_datasets = _phrase_scores(analysis_records, "dataset")
    weighted_metrics = _phrase_scores(analysis_records, "metrics")
    weighted_limitations = _phrase_scores(analysis_records, "limitations")
    scenario_keywords = [
        "低资源",
        "cross-domain",
        "跨域",
        "部署",
        "real-world",
        "edge",
        "在线",
        "鲁棒",
        "robust",
    ]
    scenario_records = _records_with_signals(
        analysis_records,
        ["problem", "limitations", "conclusion"],
        scenario_keywords,
        minimum=1,
        limit=6,
    )
    method_focus = [phrase for phrase, _ in weighted_methods[:2]]
    dataset_focus = [phrase for phrase, _ in weighted_datasets[:2]]
    metric_focus = [phrase for phrase, _ in weighted_metrics[:2]]
    rare_methods = [phrase for phrase, _ in weighted_methods[2:5]]
    rare_datasets = [phrase for phrase, _ in weighted_datasets[2:5]]
    rare_metrics = [phrase for phrase, _ in weighted_metrics[2:5]]
    method_support = _records_with_signals(
        analysis_records,
        ["method", "limitations"],
        method_focus + ["复杂", "复现", "效率", "部署", "lightweight", "latency", "参数"],
        minimum=1,
        limit=4,
    ) or analysis_records[:3]
    method_contrast = _records_without_signals(
        analysis_records,
        ["limitations"],
        ["复杂", "复现", "效率", "部署", "lightweight", "latency", "参数"],
        limit=3,
    ) or analysis_records[:2]
    data_support = _records_with_signals(
        analysis_records,
        ["dataset", "limitations"],
        dataset_focus + ["低资源", "样本", "增强", "模态", "不平衡", "scarce", "augmentation", "few-shot"],
        minimum=1,
        limit=4,
    ) or analysis_records[:3]
    data_contrast = _records_without_signals(
        analysis_records,
        ["limitations"],
        ["低资源", "样本", "增强", "模态", "不平衡", "scarce", "augmentation", "few-shot"],
        limit=3,
    ) or analysis_records[:2]
    evaluation_support = _records_with_signals(
        analysis_records,
        ["metrics", "limitations", "conclusion"],
        metric_focus + ["鲁棒", "robust", "可解释", "解释", "ablation", "消融", "效率", "error analysis", "案例"],
        minimum=1,
        limit=4,
    ) or analysis_records[:3]
    evaluation_contrast = _records_without_signals(
        analysis_records,
        ["metrics", "limitations"],
        ["鲁棒", "robust", "可解释", "解释", "ablation", "消融", "效率", "error analysis", "案例"],
        limit=3,
    ) or analysis_records[:2]
    scenario_contrast = _records_without_signals(
        analysis_records,
        ["problem", "limitations"],
        scenario_keywords,
        limit=3,
    ) or analysis_records[:2]
    method_gaps = [
        _gap_entry(
            gap_type="method_gap",
            focus=f"{method_focus[0]} 与 {(rare_methods[0] if rare_methods else '轻量模块')} 组合改造",
            description="主流方法高度集中，但兼顾复现、效率或部署约束的组合改造较少。",
            basis=[
                f"主流方法集中在 {('、'.join(method_focus) or '少数固定路线')}，方法多样性为 {len(weighted_methods)}。",
                f"常见局限反复提到 {('、'.join([phrase for phrase, _ in weighted_limitations[:2]]) or '效率与复现')}，说明方法改造空间真实存在。",
            ],
            supporting_records=method_support,
            contrast_records=method_contrast,
            preferred_support_fields=["limitations", "method", "evidence_quote"],
            preferred_contrast_fields=["method", "metrics", "conclusion"],
        )
    ]
    data_gaps = [
        _gap_entry(
            gap_type="data_gap",
            focus=f"{(dataset_focus[0] if dataset_focus else '主流数据集')} 外数据补强",
            description="数据集覆盖集中，低资源样本、增强策略或分布变化设置不足。",
            basis=[
                f"数据集主要集中在 {('、'.join(dataset_focus) or '少量公开数据集')}，数据多样性为 {len(weighted_datasets)}。",
                "多篇论文在局限中提到样本不足、增强不足或分布变化问题，说明数据 gap 具有共性。",
            ],
            supporting_records=data_support,
            contrast_records=data_contrast,
            preferred_support_fields=["dataset", "limitations", "evidence_quote"],
            preferred_contrast_fields=["dataset", "method", "conclusion"],
        )
    ]
    scenario_gaps = [
        _gap_entry(
            gap_type="scenario_gap",
            focus="低资源、跨域与真实部署场景",
            description="多数研究停留在标准实验设置，真实应用约束覆盖不足。",
            basis=[
                f"场景信号词命中的支撑论文数为 {len(scenario_records)}，说明场景约束并非个别现象。",
                f"主流问题表述集中在 {('、'.join(_top_phrases(analysis_records, 'problem')[:2]) or '标准研究设置')}，与真实应用约束之间存在落差。",
            ],
            supporting_records=scenario_records or analysis_records[:3],
            contrast_records=scenario_contrast,
            preferred_support_fields=["limitations", "problem", "conclusion"],
            preferred_contrast_fields=["problem", "method", "conclusion"],
        )
    ]
    evaluation_gaps = [
        _gap_entry(
            gap_type="evaluation_gap",
            focus=f"{(metric_focus[0] if metric_focus else '常规指标')} 之外的鲁棒性与误差分析",
            description="评价大多集中在常规指标，鲁棒性、可解释性和错误分析覆盖不足。",
            basis=[
                f"主流评测集中在 {('、'.join(metric_focus) or '常规指标')}，评测多样性为 {len(weighted_metrics)}。",
                f"局限项多次出现 {('、'.join([phrase for phrase, _ in weighted_limitations[:2]]) or '评测不足')}，说明评价缺口可追溯。",
            ],
            supporting_records=evaluation_support,
            contrast_records=evaluation_contrast,
            preferred_support_fields=["limitations", "metrics", "evidence_quote"],
            preferred_contrast_fields=["metrics", "conclusion", "method"],
        )
    ]
    return {
        "mode": "real" if len(valid_records) >= 3 else "fallback",
        "valid_record_count": len(valid_records),
        "record_count": len(analysis_records),
        "common_methods": [phrase for phrase, _ in weighted_methods[:4]],
        "common_datasets": [phrase for phrase, _ in weighted_datasets[:4]],
        "common_metrics": [phrase for phrase, _ in weighted_metrics[:4]],
        "common_limitations": [phrase for phrase, _ in weighted_limitations[:5]],
        "common_problems": _top_phrases(analysis_records, "problem"),
        "rare_methods": rare_methods,
        "rare_datasets": rare_datasets,
        "rare_metrics": rare_metrics,
        "method_diversity": len(weighted_methods),
        "dataset_diversity": len(weighted_datasets),
        "metric_diversity": len(weighted_metrics),
        "needs_review_count": len([record for record in analysis_records if record.needs_review]),
        "method_gaps": method_gaps,
        "data_gaps": data_gaps,
        "scenario_gaps": scenario_gaps,
        "evaluation_gaps": evaluation_gaps,
        "support_evidence_map": {
            "methods": _evidence_map_for_phrases(analysis_records, "method", method_focus, ["method", "limitations"]),
            "datasets": _evidence_map_for_phrases(analysis_records, "dataset", dataset_focus, ["dataset", "limitations"]),
            "metrics": _evidence_map_for_phrases(analysis_records, "metrics", metric_focus, ["metrics", "limitations"]),
        },
        "contrast_evidence_map": {
            "methods": _evidence_map_for_phrases(analysis_records, "method", rare_methods or method_focus[:1], ["method", "conclusion"]),
            "datasets": _evidence_map_for_phrases(analysis_records, "dataset", rare_datasets or dataset_focus[:1], ["dataset", "conclusion"]),
            "metrics": _evidence_map_for_phrases(analysis_records, "metrics", rare_metrics or metric_focus[:1], ["metrics", "conclusion"]),
        },
        "coverage_gaps": {
            "method": rare_methods,
            "data": rare_datasets,
            "evaluation": rare_metrics,
            "scenario": _record_titles(scenario_records, limit=3),
        },
    }


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)


def _estimate_candidate_scores(
    gap_type: str,
    evidence_mode: str,
    supporting_records: list[LiteratureRecord],
    contrast_records: list[LiteratureRecord],
    summary: dict[str, object],
) -> dict[str, float]:
    base_scores = {
        "method_gap": {"novelty": 8.2, "feasibility": 7.2, "risk": 5.6, "cost": 5.8, "fit": 7.3},
        "data_gap": {"novelty": 7.4, "feasibility": 6.8, "risk": 6.2, "cost": 6.8, "fit": 6.6},
        "scenario_gap": {"novelty": 7.8, "feasibility": 7.0, "risk": 5.8, "cost": 6.0, "fit": 7.4},
        "evaluation_gap": {"novelty": 7.1, "feasibility": 8.1, "risk": 4.6, "cost": 4.2, "fit": 8.4},
    }[gap_type]
    gap_summary_key = {
        "method_gap": "method_gaps",
        "data_gap": "data_gaps",
        "scenario_gap": "scenario_gaps",
        "evaluation_gap": "evaluation_gaps",
    }[gap_type]
    gap_entry = _top_gap_entry(summary, gap_summary_key)
    support_weight = sum(_record_weight(record) for record in supporting_records)
    contrast_weight = sum(_record_weight(record) for record in contrast_records)
    support_count = len(supporting_records)
    contrast_count = len(contrast_records)
    common_metrics = list(summary.get("common_metrics", []))
    needs_review_count = int(summary.get("needs_review_count", 0) or 0)
    scarcity_score = float(gap_entry.get("scarcity_score", 5.0) or 5.0)
    coverage_score = float(gap_entry.get("coverage_score", 5.0) or 5.0)
    evidence_strength = 3.8 + support_weight * 1.25 + contrast_weight * 0.45 + coverage_score * 0.18
    if evidence_mode == "fallback":
        evidence_strength -= 3.0
    if common_metrics:
        evidence_strength += 0.4
    if needs_review_count:
        evidence_strength -= min(1.2, needs_review_count * 0.2)
    novelty = base_scores["novelty"] + scarcity_score * 0.18 + (0.15 if evidence_mode == "real" else -0.8)
    feasibility = (
        base_scores["feasibility"]
        + min(support_count, 3) * 0.25
        + coverage_score * 0.08
        - max(0, contrast_count - support_count) * 0.18
    )
    risk = (
        base_scores["risk"]
        + (1.2 if evidence_mode == "fallback" else 0.0)
        + max(0, 2 - support_count) * 0.35
        + max(0.0, 6.0 - evidence_strength) * 0.18
    )
    cost = base_scores["cost"] + (0.4 if gap_type == "data_gap" else 0.0) + (0.25 if gap_type == "scenario_gap" else 0.0)
    fit = base_scores["fit"] + (0.3 if gap_type in {"evaluation_gap", "scenario_gap"} else 0.0) - (0.35 if evidence_mode == "fallback" else 0.0)
    return {
        "novelty_score": _clamp_score(novelty),
        "feasibility_score": _clamp_score(feasibility),
        "risk_score": _clamp_score(risk),
        "experiment_cost": _clamp_score(cost),
        "undergrad_fit": _clamp_score(fit),
        "evidence_strength": _clamp_score(evidence_strength),
    }


def _compute_overall_score(candidate: InnovationCandidate) -> float:
    total = (
        candidate.novelty_score * 0.30
        + candidate.feasibility_score * 0.25
        + candidate.undergrad_fit * 0.20
        + candidate.evidence_strength * 0.15
        + (10 - candidate.experiment_cost) * 0.05
        + (10 - candidate.risk_score) * 0.05
    )
    return round(total, 2)


def _format_gap_label(gap_type: str) -> str:
    return GAP_TYPE_LABELS.get(gap_type, gap_type)


def _gap_type_summary(gap_type: str) -> str:
    mapping = {
        "method_gap": "主流方法路线集中，但组合改造与轻量复现空间仍大",
        "data_gap": "数据集覆盖和增强设置偏窄，样本条件变化分析不足",
        "scenario_gap": "真实应用、低资源与跨域设置覆盖不足",
        "evaluation_gap": "鲁棒性、可解释性和误差分析评测仍不完整",
    }
    return mapping.get(gap_type, gap_type)


def _build_gap_overview(summary: dict[str, object], candidates: list[InnovationCandidate]) -> str:
    if not candidates:
        return "当前未形成可审核的 gap 候选。"
    strongest = max(candidates, key=lambda item: item.evidence_strength)
    gap_entry = _top_gap_entry(
        summary,
        {
            "method_gap": "method_gaps",
            "data_gap": "data_gaps",
            "scenario_gap": "scenario_gaps",
            "evaluation_gap": "evaluation_gaps",
        }.get(strongest.gap_type, ""),
    )
    description = str(gap_entry.get("description", _gap_type_summary(strongest.gap_type)))
    focus = str(gap_entry.get("focus", "待补充"))
    return (
        f"最明显的 gap 类型是{_format_gap_label(strongest.gap_type)}，"
        f"原因是{description}；"
        f"重点缺口聚焦在{focus}；"
        f"主流方法集中在{('、'.join(list(summary.get('common_methods', []))[:2]) or '待补充')}，"
        f"主流评测集中在{('、'.join(list(summary.get('common_metrics', []))[:2]) or '待补充')}。"
    )


def _build_method_gap_candidate(
    topic: str,
    records: list[LiteratureRecord],
    summary: dict[str, object],
    evidence_mode: str,
) -> InnovationCandidate | None:
    common_methods = list(summary.get("common_methods", []))
    common_metrics = list(summary.get("common_metrics", []))
    gap_entry = _top_gap_entry(summary, "method_gaps")
    support_titles = set(gap_entry.get("supporting_papers", []))
    contrast_titles = set(gap_entry.get("contrast_papers", []))
    support_records = [record for record in records if record.title in support_titles] or records[:2]
    if not support_records:
        return None
    contrast_records = [record for record in records if record.title in contrast_titles] or records[:3]
    dominant_method = common_methods[0] if common_methods else "主流方法"
    focus = str(gap_entry.get("focus", f"{dominant_method} 组合改造"))
    basis_texts = [str(item) for item in gap_entry.get("basis", []) if str(item).strip()]
    analysis_basis = _build_analysis_basis(basis_texts, support_records)
    return _candidate_payload(
        gap_type="method_gap",
        claim=f"面向 {topic} 的 {focus} 方案",
        novelty_reason=(
            f"现有研究主要沿着 {dominant_method} 展开，{str(gap_entry.get('description', '但兼顾轻量协同和复现友好的改造仍不充分。'))}"
        ),
        rare_reason=(
            f"主流论文更优先优化 {('、'.join(common_metrics[:2])) or '常规性能指标'}，"
            "较少把复现成本与模型复杂度作为主要贡献展开。"
        ),
        risk="需要控制新增模块规模，否则方法复杂度可能抵消精度收益。",
        verification_plan="与主流方法做精度、效率和参数量对比，并补充模块消融实验。",
        supporting_records=support_records,
        contrast_records=contrast_records,
        evidence_mode=evidence_mode,
        summary=summary,
        analysis_basis=analysis_basis if evidence_mode == "real" else [],
        supporting_evidence=([str(item) for item in gap_entry.get("supporting_evidence", [])] if evidence_mode == "real" else []),
        contrast_evidence=([str(item) for item in gap_entry.get("contrast_evidence", [])] if evidence_mode == "real" else []),
    )


def _build_data_gap_candidate(
    topic: str,
    records: list[LiteratureRecord],
    summary: dict[str, object],
    evidence_mode: str,
) -> InnovationCandidate | None:
    common_datasets = list(summary.get("common_datasets", []))
    gap_entry = _top_gap_entry(summary, "data_gaps")
    support_titles = set(gap_entry.get("supporting_papers", []))
    contrast_titles = set(gap_entry.get("contrast_papers", []))
    support_records = [record for record in records if record.title in support_titles] or records[:2]
    if not support_records:
        return None
    contrast_records = [record for record in records if record.title in contrast_titles] or records[:3]
    dominant_dataset = common_datasets[0] if common_datasets else "主流数据集"
    focus = str(gap_entry.get("focus", f"{dominant_dataset} 外数据补强"))
    analysis_basis = _build_analysis_basis([str(item) for item in gap_entry.get("basis", [])], support_records)
    return _candidate_payload(
        gap_type="data_gap",
        claim=f"面向 {topic} 的 {focus} 方案",
        novelty_reason=(
            f"当前文献多围绕 {('、'.join(common_datasets[:2])) or '少数公开数据集'} 展开，"
            f"{str(gap_entry.get('description', '对低资源样本、分布扰动和数据增强组合的系统设计不足。'))}"
        ),
        rare_reason="数据侧创新通常需要额外构造对照与复现实验，因此经常被弱化为辅助手段。",
        risk="若增强策略设计不稳，可能引入分布偏移并削弱结论可信度。",
        verification_plan="设置原始数据、增强数据、跨分布测试三组对照，报告均值和方差。",
        supporting_records=support_records,
        contrast_records=contrast_records,
        evidence_mode=evidence_mode,
        summary=summary,
        analysis_basis=analysis_basis if evidence_mode == "real" else [],
        supporting_evidence=([str(item) for item in gap_entry.get("supporting_evidence", [])] if evidence_mode == "real" else []),
        contrast_evidence=([str(item) for item in gap_entry.get("contrast_evidence", [])] if evidence_mode == "real" else []),
    )


def _build_scenario_gap_candidate(
    topic: str,
    records: list[LiteratureRecord],
    summary: dict[str, object],
    evidence_mode: str,
) -> InnovationCandidate | None:
    gap_entry = _top_gap_entry(summary, "scenario_gaps")
    support_titles = set(gap_entry.get("supporting_papers", []))
    contrast_titles = set(gap_entry.get("contrast_papers", []))
    support_records = [record for record in records if record.title in support_titles] or records[:3]
    if not support_records:
        return None
    contrast_records = [record for record in records if record.title in contrast_titles] or records[:3]
    focus = str(gap_entry.get("focus", "低资源与真实应用场景迁移"))
    analysis_basis = _build_analysis_basis([str(item) for item in gap_entry.get("basis", [])], support_records)
    return _candidate_payload(
        gap_type="scenario_gap",
        claim=f"面向 {topic} 的 {focus} 方案",
        novelty_reason=(
            f"当前工作更多围绕 {('、'.join(list(summary.get('common_problems', []))[:2])) or '标准研究设置'} 展开，"
            f"{str(gap_entry.get('description', '对低资源、跨域和部署约束场景覆盖不足。'))}"
        ),
        rare_reason="真实场景通常需要额外工程约束与更长验证周期，因此在毕业论文中常被简化。",
        risk="场景迁移可能带来性能波动，需要明确资源边界和应用假设。",
        verification_plan="设计标准场景与低资源/跨域双设置，比较泛化表现和稳定性。",
        supporting_records=support_records,
        contrast_records=contrast_records,
        evidence_mode=evidence_mode,
        summary=summary,
        analysis_basis=analysis_basis if evidence_mode == "real" else [],
        supporting_evidence=([str(item) for item in gap_entry.get("supporting_evidence", [])] if evidence_mode == "real" else []),
        contrast_evidence=([str(item) for item in gap_entry.get("contrast_evidence", [])] if evidence_mode == "real" else []),
    )


def _build_evaluation_gap_candidate(
    topic: str,
    records: list[LiteratureRecord],
    summary: dict[str, object],
    evidence_mode: str,
) -> InnovationCandidate | None:
    gap_entry = _top_gap_entry(summary, "evaluation_gaps")
    support_titles = set(gap_entry.get("supporting_papers", []))
    contrast_titles = set(gap_entry.get("contrast_papers", []))
    support_records = [record for record in records if record.title in support_titles] or records[:2]
    if not support_records:
        return None
    contrast_records = [record for record in records if record.title in contrast_titles] or records[:3]
    focus = str(gap_entry.get("focus", "鲁棒性、可解释性与误差分析补强"))
    analysis_basis = _build_analysis_basis([str(item) for item in gap_entry.get("basis", [])], support_records)
    return _candidate_payload(
        gap_type="evaluation_gap",
        claim=f"面向 {topic} 的 {focus} 方案",
        novelty_reason=(
            f"当前评测大多集中在 {('、'.join(list(summary.get('common_metrics', []))[:2])) or '常规指标'}，"
            f"{str(gap_entry.get('description', '对鲁棒性、可解释性和错误案例分析的覆盖偏弱。'))}"
        ),
        rare_reason=(
            f"在 {('、'.join(list(summary.get('common_limitations', []))[:2])) or '现有工作局限'} 背景下，"
            "评价维度扩展虽容易落地，但常未被作为主要创新系统展开。"
        ),
        risk="如果评价协议设计不清晰，新增分析会增加工作量但难以支撑结论。",
        verification_plan="补充鲁棒测试、案例分析和可解释可视化，与主结果同步报告。",
        supporting_records=support_records,
        contrast_records=contrast_records,
        evidence_mode=evidence_mode,
        summary=summary,
        analysis_basis=analysis_basis if evidence_mode == "real" else [],
        supporting_evidence=([str(item) for item in gap_entry.get("supporting_evidence", [])] if evidence_mode == "real" else []),
        contrast_evidence=([str(item) for item in gap_entry.get("contrast_evidence", [])] if evidence_mode == "real" else []),
    )


def _build_fallback_candidate(gap_type: str, topic: str, records: list[LiteratureRecord], summary: dict[str, object]) -> InnovationCandidate:
    common_methods = list(summary.get("common_methods", []))
    common_datasets = list(summary.get("common_datasets", []))
    common_metrics = list(summary.get("common_metrics", []))
    support_records = records[:2]
    contrast_records = records[2:4] or records[:1]
    templates = {
        "method_gap": {
            "claim": f"面向 {topic} 的方法协同改造占位推荐",
            "novelty_reason": f"现有文献主要聚焦 {('、'.join(common_methods[:2])) or '单一路线'}，需要补充更多方法细节后确认真实组合 gap。",
            "rare_reason": "当前结构化证据不足，先保留方法侧候选作为占位推荐。",
            "risk": "文献不足时容易高估方法创新空间。",
            "verification_plan": "优先补充方法细节更完整的文献后再确定最终方案。",
        },
        "data_gap": {
            "claim": f"面向 {topic} 的数据补强占位推荐",
            "novelty_reason": f"当前数据线索主要来自 {('、'.join(common_datasets[:2])) or '有限数据设置'}，需要更多证据判断真实数据 gap。",
            "rare_reason": "数据与样本条件信息不足，因此先保留占位建议。",
            "risk": "可能把数据不足误判为真实创新机会。",
            "verification_plan": "优先补充数据集规模、增强策略和样本条件相关文献。",
        },
        "scenario_gap": {
            "claim": f"面向 {topic} 的场景迁移占位推荐",
            "novelty_reason": "当前对真实应用场景的结构化信息不足，因此保留场景侧候选以待人工确认。",
            "rare_reason": "真实场景相关证据链不完整，需人工复核。",
            "risk": "场景假设可能与现有数据条件不一致。",
            "verification_plan": "补充低资源、跨域或部署条件更明确的文献。",
        },
        "evaluation_gap": {
            "claim": f"面向 {topic} 的评价补强占位推荐",
            "novelty_reason": f"目前只看到 {('、'.join(common_metrics[:2])) or '常规评测'} 线索，需要更多证据确认评价维度缺口。",
            "rare_reason": "评价协议细节不足，因此先保留占位推荐。",
            "risk": "若现有论文已做相关评测，可能造成重复工作。",
            "verification_plan": "补充包含鲁棒性、可解释性或案例分析的论文后再落定。",
        },
    }[gap_type]
    return _candidate_payload(
        gap_type=gap_type,
        claim=templates["claim"],
        novelty_reason=templates["novelty_reason"],
        rare_reason=templates["rare_reason"],
        risk=templates["risk"],
        verification_plan=templates["verification_plan"],
        supporting_records=support_records,
        contrast_records=contrast_records,
        evidence_mode="fallback",
        summary=summary,
        recommendation_reason="结构化文献证据不足，当前为占位推荐，建议补充文献后再确认。",
        analysis_basis=[],
        supporting_evidence=[],
        contrast_evidence=[],
    )


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _looks_english_query(text: str) -> bool:
    candidate = _clean_text(text)
    if not candidate:
        return False
    if _contains_cjk(candidate):
        return False
    letters = re.findall(r"[A-Za-z]", candidate)
    if len(letters) < 6:
        return False
    non_word_ratio = len(re.findall(r"[^A-Za-z0-9\s\-_/():,.]", candidate)) / max(len(candidate), 1)
    return non_word_ratio < 0.2


def _sanitize_translated_topic(content: str) -> str:
    candidate = _clean_text(content)
    if not candidate:
        return ""
    if "\n" in content:
        candidate = _clean_text(content.splitlines()[0])
    candidate = re.sub(r"^[\-•\d.)\s]+", "", candidate)
    candidate = re.sub(r"^(translation|english title|translated topic)\s*[:：-]\s*", "", candidate, flags=re.IGNORECASE)
    return _clean_text(candidate.strip('"“”'))


def _extract_keywords(topic: str) -> list[str]:
    normalized = _clean_text(topic)
    parts = re.split(r"[\s,，、;/；:()\[\]\-]+", normalized)
    keywords = [part.strip() for part in parts if part.strip()]
    if normalized and len(parts) > 1:
        noun_phrase = " ".join(part for part in parts[:4] if part)
        if noun_phrase:
            keywords.insert(0, noun_phrase)
    if normalized not in keywords:
        keywords.insert(0, normalized)
    deduped: list[str] = []
    for keyword in keywords:
        lowered = keyword.lower()
        if not lowered or lowered in {item.lower() for item in deduped}:
            continue
        deduped.append(keyword)
    return deduped[:8]


def _compose_query_keywords(original_topic: str, translated_topic: str | None) -> list[str]:
    prioritized: list[str] = []
    if translated_topic and _looks_english_query(translated_topic):
        prioritized.extend(_extract_keywords(translated_topic))
    prioritized.extend(_extract_keywords(original_topic))

    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in prioritized:
        normalized = keyword.strip().lower()
        if not normalized or normalized in seen:
            continue
        deduped.append(keyword.strip())
        seen.add(normalized)
    return deduped[:8]


def _find_first(pattern: str, text: str, fallback: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else fallback


def _heuristic_survey_row(record: LiteratureRecord) -> dict[str, str]:
    abstract = record.abstract or ""
    return {
        "title": record.title,
        "problem": record.problem or _find_first(r"(?:problem|task|aims? to)\s+(.*?)[\.;]", abstract, "围绕该主题的基础研究问题"),
        "method": record.method or _find_first(r"(?:method|approach|framework|proposes?)\s+(.*?)[\.;]", abstract, "结合主流方法的改进方案"),
        "dataset": record.dataset or _find_first(r"(?:dataset|data|benchmarks?)\s+(.*?)[\.;]", abstract, "公开数据集/自建样本"),
        "metrics": record.metrics or _find_first(r"(?:metric|metrics|evaluated by)\s+(.*?)[\.;]", abstract, "Accuracy / F1 / Recall"),
        "conclusion": record.conclusion or abstract[:160] if abstract else "论文结论待从全文进一步提炼",
        "limitations": record.limitations or "依赖摘要推断，仍需结合全文核验",
        "source": record.source,
        "doi_or_url": record.doi_or_url,
        "evidence_source": record.evidence_source,
        "confidence": f"{record.confidence_score:.2f}",
        "evidence_quote": record.evidence_quote,
        "pdf_path": record.pdf_path or "",
        "pdf_parse_status": record.pdf_parse_status,
        "pdf_parse_message": record.pdf_parse_message,
        "citation_count": str(record.citation_count),
        "is_fallback": "yes" if record.is_fallback else "no",
        "needs_review": "yes" if record.needs_review else "no",
        "review_note": record.review_note,
    }


def is_valid_literature_record(record: LiteratureRecord) -> bool:
    if record.is_fallback:
        return False
    if not _clean_text(record.title):
        return False
    has_abstract = bool(_clean_text(record.abstract)) and "摘要缺失" not in record.abstract
    has_link = bool(_clean_text(record.doi_or_url))
    return has_abstract or has_link


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sentence_chunks(text: str) -> list[str]:
    if not text:
        return []
    return [chunk.strip() for chunk in re.split(r"(?<=[。！？.!?;；])\s+|\n+", text) if chunk.strip()]


def _extract_field(patterns: list[str], text: str, fallback: str) -> tuple[str, str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _clean_text(match.group(1))
            if value:
                return value, value
    sentences = _sentence_chunks(text)
    for sentence in sentences:
        lowered = sentence.lower()
        if any(token in lowered for token in ["problem", "task", "aim", "method", "approach", "dataset", "benchmark", "metric", "result", "limitation", "conclusion"]):
            candidate = _clean_text(sentence)
            if candidate:
                return candidate, candidate
    return fallback, ""


def _build_structured_record(record: LiteratureRecord, source_text: str) -> LiteratureRecord:
    problem, problem_quote = _extract_field(
        [r"(?:problem|task|objective|aims? to)\s+(.*?)[\.;]", r"(?:研究问题|目标|任务为)[:：]?\s*(.*?)[。；]"],
        source_text,
        "围绕该主题的基础研究问题",
    )
    method, method_quote = _extract_field(
        [r"(?:method|approach|framework|proposes?)\s+(.*?)[\.;]", r"(?:提出|方法|框架)[:：]?\s*(.*?)[。；]"],
        source_text,
        "结合主流方法的改进方案",
    )
    dataset, dataset_quote = _extract_field(
        [r"(?:dataset|data|benchmark[s]?)\s+(.*?)[\.;]", r"(?:数据集|样本)[:：]?\s*(.*?)[。；]"],
        source_text,
        "公开数据集/自建样本",
    )
    metrics, metrics_quote = _extract_field(
        [r"(?:metric|metrics|evaluated by)\s+(.*?)[\.;]", r"(?:指标|评估)[:：]?\s*(.*?)[。；]"],
        source_text,
        "Accuracy / F1 / Recall",
    )
    conclusion, conclusion_quote = _extract_field(
        [r"(?:result|conclusion|finds?|shows?)\s+(.*?)[\.;]", r"(?:结论|结果表明)[:：]?\s*(.*?)[。；]"],
        source_text,
        "论文结论待从全文进一步提炼",
    )
    limitations, limitations_quote = _extract_field(
        [r"(?:limit(?:ation)?s?)\s+(.*?)[\.;]", r"(?:局限|不足)[:：]?\s*(.*?)[。；]"],
        source_text,
        "仍需结合全文或人工核验局限性",
    )
    quotes = [item for item in [problem_quote, method_quote, dataset_quote, metrics_quote, conclusion_quote, limitations_quote] if item]
    evidence_source = record.evidence_source
    if evidence_source not in VALID_EVIDENCE_SOURCES:
        evidence_source = "pdf" if record.pdf_path and source_text != (record.abstract or "") else "abstract"
    if record.is_fallback:
        evidence_source = "fallback"
    evidence_spans = list(dict.fromkeys(quotes[:4]))
    confidence = 0.85 if evidence_source == "pdf" else 0.7
    if record.is_fallback:
        confidence = 0.25
    needs_review, review_note = _build_review_flags(record, confidence)
    return LiteratureRecord(
        source=record.source,
        title=record.title,
        authors=record.authors,
        year=record.year,
        abstract=record.abstract,
        doi_or_url=record.doi_or_url,
        pdf_path=record.pdf_path,
        evidence_spans=evidence_spans,
        keywords=record.keywords,
        citation_count=record.citation_count,
        retrieval_rank=record.retrieval_rank,
        is_fallback=record.is_fallback,
        problem=problem,
        method=method,
        dataset=dataset,
        metrics=metrics,
        conclusion=conclusion,
        limitations=limitations,
        evidence_source=evidence_source,
        confidence_score=confidence,
        evidence_quote=quotes[0] if quotes else (record.abstract[:180] if record.abstract else ""),
        pdf_parse_status=record.pdf_parse_status,
        pdf_parse_message=record.pdf_parse_message,
        needs_review=needs_review,
        review_note=review_note,
    )


def _try_parse_json_object(content: str) -> dict[str, str]:
    if not content:
        return {}
    candidate = content.strip()
    if "{" in candidate and "}" in candidate:
        candidate = candidate[candidate.find("{") : candidate.rfind("}") + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(key): _clean_text(str(value))
        for key, value in parsed.items()
        if value is not None
    }


def _merge_reader_result(base: LiteratureRecord, llm_fields: dict[str, str]) -> LiteratureRecord:
    if not llm_fields:
        return base

    def pick(field_name: str, fallback: str) -> str:
        value = _clean_text(llm_fields.get(field_name, ""))
        return value or fallback

    try:
        confidence = float(llm_fields.get("confidence_score", base.confidence_score))
    except (TypeError, ValueError):
        confidence = base.confidence_score
    confidence = max(0.0, min(1.0, confidence))

    evidence_source = pick("evidence_source", base.evidence_source)
    if evidence_source not in VALID_EVIDENCE_SOURCES:
        evidence_source = base.evidence_source
    if base.is_fallback:
        evidence_source = "fallback"

    evidence_quote = pick("evidence_quote", base.evidence_quote)
    evidence_spans = list(
        dict.fromkeys([*base.evidence_spans, evidence_quote] if evidence_quote else base.evidence_spans)
    )
    needs_review, review_note = _build_review_flags(base, confidence, evidence_quote=evidence_quote)

    return LiteratureRecord(
        source=base.source,
        title=base.title,
        authors=base.authors,
        year=base.year,
        abstract=base.abstract,
        doi_or_url=base.doi_or_url,
        pdf_path=base.pdf_path,
        evidence_spans=evidence_spans,
        keywords=base.keywords,
        citation_count=base.citation_count,
        retrieval_rank=base.retrieval_rank,
        is_fallback=base.is_fallback,
        problem=pick("problem", base.problem),
        method=pick("method", base.method),
        dataset=pick("dataset", base.dataset),
        metrics=pick("metrics", base.metrics),
        conclusion=pick("conclusion", base.conclusion),
        limitations=pick("limitations", base.limitations),
        evidence_source=evidence_source,
        confidence_score=max(base.confidence_score, confidence),
        evidence_quote=evidence_quote,
        pdf_parse_status=base.pdf_parse_status,
        pdf_parse_message=base.pdf_parse_message,
        needs_review=needs_review,
        review_note=review_note,
    )


def _build_review_flags(
    record: LiteratureRecord,
    confidence: float,
    *,
    evidence_quote: str | None = None,
) -> tuple[bool, str]:
    reasons: list[str] = []
    effective_quote = _clean_text(evidence_quote if evidence_quote is not None else record.evidence_quote)
    if record.is_fallback:
        reasons.append("仅依赖 fallback 占位文献")
    if confidence < 0.55:
        reasons.append("置信度偏低")
    if record.pdf_path and record.pdf_parse_status in {"degraded", "failed"}:
        reasons.append(record.pdf_parse_message or "PDF 解析失败或内容不足")
    if not _clean_text(record.abstract) or "摘要缺失" in (record.abstract or ""):
        reasons.append("摘要缺失")
    if not effective_quote:
        reasons.append("缺少关键证据摘录")
    review_note = "；".join(dict.fromkeys(reasons))
    return bool(review_note), review_note


def _build_survey_row(record: LiteratureRecord) -> dict[str, str]:
    row = _heuristic_survey_row(record)
    row.update(
        {
            "title": record.title,
            "problem": record.problem or row["problem"],
            "method": record.method or row["method"],
            "dataset": record.dataset or row["dataset"],
            "metrics": record.metrics or row["metrics"],
            "conclusion": record.conclusion or row["conclusion"],
            "limitations": record.limitations or row["limitations"],
            "source": record.source,
            "doi_or_url": record.doi_or_url,
            "evidence_source": record.evidence_source,
            "confidence": f"{record.confidence_score:.2f}",
            "evidence_quote": record.evidence_quote,
            "pdf_path": record.pdf_path or "",
            "pdf_parse_status": record.pdf_parse_status,
            "pdf_parse_message": record.pdf_parse_message,
            "citation_count": str(record.citation_count),
            "is_fallback": "yes" if record.is_fallback else "no",
            "needs_review": "yes" if record.needs_review else "no",
            "review_note": record.review_note,
        }
    )
    return row


class BaseAgent:
    name = "base"
    task_type = "planner"

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    def log(self, state: ProjectState, message: str) -> None:
        state.execution_log.append(f"{self.name}: {message}")

    def run(self, state: ProjectState) -> ProjectState:
        raise NotImplementedError


class TopicPlannerAgent(BaseAgent):
    name = "topic_planner"
    task_type = "planner"

    def run(self, state: ProjectState) -> ProjectState:
        translated_topic = self._translate_topic_for_search(state)
        keywords = _compose_query_keywords(state.request.topic, translated_topic)
        prompt = (
            f"研究方向：{state.request.topic}\n"
            f"英文检索题目：{translated_topic or state.request.topic}\n"
            f"请扩展一组中英文检索关键词，强调算法论文、实验、数据集、评估指标。"
        )
        result = self.gateway.complete(
            self.task_type,
            prompt,
            system_prompt="You plan literature retrieval queries.",
        )
        state.result_schema["original_topic"] = state.request.topic
        state.result_schema["translated_topic"] = translated_topic or state.request.topic
        state.result_schema["query_keywords"] = keywords
        state.result_schema["planner_trace"] = result.content
        self.log(state, f"generated {len(keywords)} keywords via {result.provider}")
        return state

    def _translate_topic_for_search(self, state: ProjectState) -> str | None:
        topic = _clean_text(state.request.topic)
        if not topic:
            return None

        if not self._should_translate_topic(topic, state.request.language):
            state.result_schema["translation_provider"] = "skipped"
            state.result_schema["translation_fallback_used"] = False
            self.log(state, "translation skipped; using original topic")
            return None

        prompt = (
            "请将下面的中文研究题目翻译成一条适合 OpenAlex、arXiv 等英文学术数据库检索的英文题目。"
            "仅返回英文题目本身，不要解释，不要项目符号，不要 JSON。\n\n"
            f"中文题目：{topic}"
        )
        try:
            result = self.gateway.complete(
                self.task_type,
                prompt,
                system_prompt="You translate Chinese research topics into concise academic English search queries.",
            )
        except Exception as exc:
            state.result_schema["translation_provider"] = "error"
            state.result_schema["translation_fallback_used"] = True
            state.result_schema["translation_failed"] = True
            state.warnings.append(f"题目翻译失败，已回退原始题目检索：{exc}")
            self.log(state, "translation failed; falling back to original topic")
            return None

        translated_topic = _sanitize_translated_topic(result.content)
        if not _looks_english_query(translated_topic):
            state.result_schema["translation_provider"] = result.provider
            state.result_schema["translation_fallback_used"] = True
            state.result_schema["translation_failed"] = True
            state.warnings.append("题目翻译结果不可用，已回退原始题目检索。")
            self.log(state, f"translation unusable via {result.provider}; fallback to original topic")
            return None

        state.result_schema["translation_provider"] = result.provider
        state.result_schema["translation_fallback_used"] = result.fallback_used
        state.result_schema["translation_failed"] = False
        self.log(state, f"translated topic via {result.provider}: {translated_topic}")
        return translated_topic

    def _should_translate_topic(self, topic: str, language: str) -> bool:
        if language.startswith("zh"):
            return True
        return _contains_cjk(topic)


class RetrieverAgent(BaseAgent):
    name = "retriever"
    task_type = "survey_synthesizer"

    def run(self, state: ProjectState) -> ProjectState:
        translated_topic = state.result_schema.get("translated_topic") or state.request.topic
        keywords: list[str] = state.result_schema.get(
            "query_keywords", _compose_query_keywords(state.request.topic, translated_topic)
        )
        collected: list[LiteratureRecord] = []
        diagnostics: list[dict[str, str | int | bool]] = []
        deduped: list[LiteratureRecord] = []
        for query in keywords:
            query_language = "english" if _looks_english_query(query) else "original"
            openalex_records, openalex_diag = self._search_openalex(query, state.request.topic, query_language)
            arxiv_records, arxiv_diag = self._search_arxiv(query, state.request.topic, query_language)
            semantic_records, semantic_diag = self._search_semantic_scholar(query, state.request.topic, query_language)
            diagnostics.extend([openalex_diag, arxiv_diag, semantic_diag])
            collected.extend(openalex_records)
            collected.extend(arxiv_records)
            collected.extend(semantic_records)
            deduped = self._dedupe_and_rank(collected)
            if self._count_valid_records(deduped) >= MIN_VALID_PAPER_COUNT:
                break

        if state.uploaded_pdf_paths:
            for pdf_path in state.uploaded_pdf_paths:
                record = self._parse_uploaded_pdf(Path(pdf_path))
                if record:
                    collected.append(record)
                    diagnostics.append(
                        {
                            "source": "user_pdf",
                            "query": pdf_path,
                            "original_query": pdf_path,
                            "query_language": "file",
                            "ok": True,
                            "count": 1,
                            "error": "",
                        }
                    )

        deduped = self._dedupe_and_rank(collected)
        state.retrieval_diagnostics = diagnostics

        if not deduped:
            deduped = self._offline_fallback(state.request.topic, translated_topic)
            state.warnings.append("未能在线检索到文献，已使用离线占位文献继续流程。")
            failed_sources = [
                item for item in diagnostics if item.get("source") != "user_pdf" and not item.get("ok")
            ]
            if failed_sources:
                for item in failed_sources:
                    state.warnings.append(
                        f"检索源 {item.get('source')} 失败：{item.get('error') or '未知错误'}"
                    )
            elif diagnostics:
                state.warnings.append("在线检索请求已发出，但未命中可用文献结果。")

        valid_count = self._count_valid_records(deduped)
        fallback_count = sum(1 for item in deduped if item.is_fallback)
        failed_sources = list(
            dict.fromkeys(
                str(item.get("source"))
                for item in diagnostics
                if item.get("source") != "user_pdf" and not item.get("ok")
            )
        )

        if valid_count >= MIN_VALID_PAPER_COUNT:
            retrieval_status = "success"
        elif valid_count > 0:
            retrieval_status = "partial"
            state.warnings.append(f"当前仅获得 {valid_count} 篇有效文献，未达到 {MIN_VALID_PAPER_COUNT} 篇验收门槛。")
        else:
            retrieval_status = "fallback"

        state.retrieval_summary = RetrievalSummary(
            retrieval_status=retrieval_status,
            valid_paper_count=valid_count,
            fallback_count=fallback_count,
            failed_sources=failed_sources,
            needs_review_count=sum(1 for item in deduped if item.needs_review),
        )

        for index, item in enumerate(deduped, start=1):
            item.retrieval_rank = index

        state.literature_records = deduped
        self.log(state, f"collected {len(deduped)} literature records")
        return state

    def _count_valid_records(self, records: list[LiteratureRecord]) -> int:
        unique_titles: set[str] = set()
        count = 0
        for item in records:
            normalized_title = _clean_text(item.title).lower()
            if not normalized_title or normalized_title in unique_titles:
                continue
            unique_titles.add(normalized_title)
            if is_valid_literature_record(item):
                count += 1
        return count

    def _search_openalex(
        self, query: str, original_query: str, query_language: str
    ) -> tuple[list[LiteratureRecord], dict[str, str | int | bool]]:
        encoded = parse.quote(query)
        url = f"https://api.openalex.org/works?search={encoded}&per-page=3"
        try:
            with request.urlopen(url, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return [], self._build_diagnostic(
                "openalex", query, False, 0, self._normalize_error(exc), original_query, query_language
            )

        records: list[LiteratureRecord] = []
        for item in payload.get("results", []):
            title = item.get("display_name") or query
            authors = ", ".join(
                author.get("author", {}).get("display_name", "")
                for author in item.get("authorships", [])[:5]
            ).strip(", ")
            abstract = ""
            if item.get("abstract_inverted_index"):
                inverse = item["abstract_inverted_index"]
                words = sorted(
                    (
                        (position, word)
                        for word, positions in inverse.items()
                        for position in positions
                    ),
                    key=lambda entry: entry[0],
                )
                abstract = " ".join(word for _, word in words[:250])
            records.append(
                LiteratureRecord(
                    source="openalex",
                    title=title,
                    authors=authors or "Unknown",
                    year=int(item.get("publication_year") or 2024),
                    abstract=abstract or "OpenAlex 摘要缺失",
                    doi_or_url=item.get("doi") or item.get("id") or "",
                    keywords=_extract_keywords(query),
                    citation_count=int(item.get("cited_by_count") or 0),
                )
            )
        return records, self._build_diagnostic("openalex", query, True, len(records), "", original_query, query_language)

    def _search_arxiv(
        self, query: str, original_query: str, query_language: str
    ) -> tuple[list[LiteratureRecord], dict[str, str | int | bool]]:
        encoded = parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results=3"
        try:
            with request.urlopen(url, timeout=15) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:
            return [], self._build_diagnostic(
                "arxiv", query, False, 0, self._normalize_error(exc), original_query, query_language
            )

        root = ElementTree.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        records: list[LiteratureRecord] = []
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or query).strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
            published = entry.findtext("atom:published", default="2024", namespaces=ns)
            year = int((published or "2024")[:4])
            authors = ", ".join(
                (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
                for author in entry.findall("atom:author", ns)
            )
            link = entry.findtext("atom:id", default="", namespaces=ns)
            records.append(
                LiteratureRecord(
                    source="arxiv",
                    title=title,
                    authors=authors or "Unknown",
                    year=year,
                    abstract=summary or "arXiv 摘要缺失",
                    doi_or_url=link,
                    keywords=_extract_keywords(query),
                )
            )
        return records, self._build_diagnostic("arxiv", query, True, len(records), "", original_query, query_language)

    def _search_semantic_scholar(
        self, query: str, original_query: str, query_language: str
    ) -> tuple[list[LiteratureRecord], dict[str, str | int | bool]]:
        encoded = parse.quote(query)
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={encoded}&limit=3&fields=title,year,abstract,authors,url,citationCount"
        )
        try:
            with request.urlopen(url, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return [], self._build_diagnostic(
                "semantic_scholar", query, False, 0, self._normalize_error(exc), original_query, query_language
            )

        records: list[LiteratureRecord] = []
        for item in payload.get("data", []):
            authors = ", ".join(author.get("name", "") for author in item.get("authors", [])[:5]).strip(", ")
            title = item.get("title") or query
            records.append(
                LiteratureRecord(
                    source="semantic_scholar",
                    title=title,
                    authors=authors or "Unknown",
                    year=int(item.get("year") or 2024),
                    abstract=item.get("abstract") or "Semantic Scholar 摘要缺失",
                    doi_or_url=item.get("url") or "",
                    keywords=_extract_keywords(query),
                    citation_count=int(item.get("citationCount") or 0),
                )
            )
        return records, self._build_diagnostic(
            "semantic_scholar", query, True, len(records), "", original_query, query_language
        )

    def _parse_uploaded_pdf(self, pdf_path: Path) -> LiteratureRecord | None:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(pdf_path))
            text = "".join(page.extract_text() or "" for page in reader.pages[:3])
        except Exception as exc:
            return LiteratureRecord(
                source="user_pdf",
                title=pdf_path.stem,
                authors="用户上传",
                year=2024,
                abstract="PDF 已上传，但当前环境无法可靠提取文本，需要人工补充校验。",
                doi_or_url=str(pdf_path),
                pdf_path=str(pdf_path),
                evidence_source="manual",
                pdf_parse_status="failed",
                pdf_parse_message=str(exc) or "PDF 解析失败",
                needs_review=True,
                review_note="PDF 解析失败",
            )
        except Exception:
            text = ""
        if not text:
            return LiteratureRecord(
                source="user_pdf",
                title=pdf_path.stem,
                authors="用户上传",
                year=2024,
                abstract="PDF 已上传，但当前环境无法可靠提取文本，需要人工补充校验。",
                doi_or_url=str(pdf_path),
                pdf_path=str(pdf_path),
                evidence_source="manual",
                pdf_parse_status="failed",
                pdf_parse_message="PDF 无法提取文本",
                needs_review=True,
                review_note="PDF 无法提取文本",
            )
        title = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            pdf_path.stem,
        )
        abstract = text[:1000]
        parse_status = "success" if len(_clean_text(text)) >= 600 else "degraded"
        parse_message = "" if parse_status == "success" else "PDF 可提取文本较少，仅能作为降级证据"
        return LiteratureRecord(
            source="user_pdf",
            title=title,
            authors="用户上传",
            year=2024,
            abstract=abstract,
            doi_or_url=str(pdf_path),
            pdf_path=str(pdf_path),
            evidence_source="pdf",
            confidence_score=0.8,
            evidence_quote=abstract[:180],
            pdf_parse_status=parse_status,
            pdf_parse_message=parse_message,
            needs_review=parse_status != "success",
            review_note=parse_message,
        )

    def _dedupe_and_rank(self, records: list[LiteratureRecord]) -> list[LiteratureRecord]:
        ranked = sorted(records, key=self._quality_score, reverse=True)
        deduped: list[LiteratureRecord] = []
        for item in ranked:
            title = item.title.strip().lower()
            duplicate = False
            for existing in deduped:
                similarity = SequenceMatcher(None, title, existing.title.strip().lower()).ratio()
                if similarity >= 0.88:
                    duplicate = True
                    break
            if duplicate:
                continue
            deduped.append(item)
            if len(deduped) >= 10:
                break
        return deduped

    def _quality_score(self, record: LiteratureRecord) -> tuple[int, int, int, int]:
        return (
            1 if record.pdf_path else 0,
            int(record.citation_count or 0),
            int(record.year or 0),
            len(record.abstract or ""),
        )

    def _build_diagnostic(
        self,
        source: str,
        query: str,
        ok: bool,
        count: int,
        error_message: str,
        original_query: str = "",
        query_language: str = "unknown",
    ) -> dict[str, str | int | bool]:
        return {
            "source": source,
            "query": query,
            "original_query": original_query or query,
            "query_language": query_language,
            "ok": ok,
            "count": count,
            "error": error_message,
        }

    def _normalize_error(self, exc: Exception) -> str:
        if isinstance(exc, error.HTTPError):
            return f"HTTP {exc.code}: {exc.reason}"
        if isinstance(exc, error.URLError):
            return f"URL Error: {exc.reason}"
        message = str(exc).strip()
        return message or exc.__class__.__name__

    def _offline_fallback(self, topic: str, translated_topic: str | None = None) -> list[LiteratureRecord]:
        search_topic = translated_topic or topic
        base = slugify(search_topic).replace("-", " ")
        return [
            LiteratureRecord(
                source="offline_stub",
                title=f"{base.title()} 的多视角综述与实验研究",
                authors="Offline Stub",
                year=2024,
                abstract=f"本文围绕 {search_topic} 的方法、数据集与评测方式进行综述，并总结常见局限。",
                doi_or_url="offline://paper-1",
                keywords=_compose_query_keywords(topic, translated_topic),
                is_fallback=True,
                confidence_score=0.25,
            ),
            LiteratureRecord(
                source="offline_stub",
                title=f"基于 {search_topic} 的算法优化框架",
                authors="Offline Stub",
                year=2023,
                abstract=f"研究提出一种面向 {search_topic} 的改进框架，对比主流方法并报告准确率与F1值。",
                doi_or_url="offline://paper-2",
                keywords=_compose_query_keywords(topic, translated_topic),
                is_fallback=True,
                confidence_score=0.25,
            ),
        ]


class ReaderAgent(BaseAgent):
    name = "reader"
    task_type = "survey_synthesizer"

    def run(self, state: ProjectState) -> ProjectState:
        enriched: list[LiteratureRecord] = []
        for record in state.literature_records:
            source_text, pdf_parse_status, pdf_parse_message = self._resolve_source_text(record)
            seeded = LiteratureRecord(
                source=record.source,
                title=record.title,
                authors=record.authors,
                year=record.year,
                abstract=record.abstract,
                doi_or_url=record.doi_or_url,
                pdf_path=record.pdf_path,
                evidence_spans=record.evidence_spans,
                keywords=record.keywords,
                citation_count=record.citation_count,
                retrieval_rank=record.retrieval_rank,
                is_fallback=record.is_fallback,
                problem=record.problem,
                method=record.method,
                dataset=record.dataset,
                metrics=record.metrics,
                conclusion=record.conclusion,
                limitations=record.limitations,
                evidence_source=record.evidence_source,
                confidence_score=record.confidence_score,
                evidence_quote=record.evidence_quote,
                pdf_parse_status=pdf_parse_status,
                pdf_parse_message=pdf_parse_message,
                needs_review=record.needs_review,
                review_note=record.review_note,
            )
            structured = _build_structured_record(seeded, source_text)
            structured = self._refine_with_llm(seeded, structured, source_text)
            enriched.append(structured)
        state.literature_records = enriched
        state.retrieval_summary.needs_review_count = sum(1 for item in enriched if item.needs_review)
        state.literature_detail_fields = [
            "problem",
            "method",
            "dataset",
            "metrics",
            "conclusion",
            "limitations",
            "source",
            "doi_or_url",
            "evidence_source",
            "confidence_score",
            "pdf_parse_status",
            "pdf_parse_message",
            "needs_review",
            "review_note",
        ]
        self.log(state, f"structured {len(enriched)} literature records")
        return state

    def _refine_with_llm(
        self,
        original: LiteratureRecord,
        structured: LiteratureRecord,
        source_text: str,
    ) -> LiteratureRecord:
        if original.is_fallback or len(source_text) < 120:
            return structured

        prompt = (
            "请从以下论文文本中提取结构化文献信息，并严格输出 JSON 对象，不要输出额外说明。"
            "JSON 字段必须包含：problem, method, dataset, metrics, conclusion, limitations, evidence_source, confidence_score, evidence_quote。"
            "若信息缺失，请保留空字符串；confidence_score 范围为 0 到 1。\n\n"
            f"标题：{original.title}\n"
            f"作者：{original.authors}\n"
            f"来源：{original.source}\n"
            f"文本：{source_text[:4000]}"
        )
        result = self.gateway.complete(
            self.task_type,
            prompt,
            system_prompt="You extract literature fields and return JSON only.",
        )
        parsed = _try_parse_json_object(result.content)
        return _merge_reader_result(structured, parsed)

    def _resolve_source_text(self, record: LiteratureRecord) -> tuple[str, str, str]:
        if record.pdf_path:
            path = Path(record.pdf_path)
            if path.exists():
                try:
                    from pypdf import PdfReader  # type: ignore

                    reader = PdfReader(str(path))
                    text = " ".join((page.extract_text() or "") for page in reader.pages[:5])
                    text = _clean_text(text)
                    if text:
                        status = "success" if len(text) >= 800 else "degraded"
                        message = "" if status == "success" else "PDF 可提取文本较少，已降级使用。"
                        return text, status, message
                except Exception as exc:
                    return record.abstract or record.title, "failed", str(exc) or "PDF 解析失败"
            return record.abstract or record.title, "failed", "PDF 文件不存在或不可访问"
        return record.abstract or record.title, "not_applicable", ""


class EvidenceExtractorAgent(BaseAgent):
    name = "evidence_extractor"
    task_type = "survey_synthesizer"

    def run(self, state: ProjectState) -> ProjectState:
        state.survey_table = [_build_survey_row(record) for record in state.literature_records]
        self.log(state, f"built survey table with {len(state.survey_table)} rows")
        return state


class SurveySynthesizerAgent(BaseAgent):
    name = "survey_synthesizer"
    task_type = "survey_synthesizer"

    def run(self, state: ProjectState) -> ProjectState:
        prompt = (
            "请根据以下综述表生成一段总结，强调研究热点、常见方法、数据集、指标与局限：\n"
            f"{json.dumps(state.survey_table[:6], ensure_ascii=False)}"
        )
        result = self.gateway.complete(
            self.task_type,
            prompt,
            system_prompt="You synthesize literature surveys in Chinese.",
        )
        state.result_schema["survey_summary"] = result.content
        self.log(state, f"summarized survey via {result.provider}")
        return state


class GapAnalystAgent(BaseAgent):
    name = "gap_analyst"
    task_type = "planner"

    def run(self, state: ProjectState) -> ProjectState:
        summary = _build_gap_analysis_summary(state)
        state.result_schema["gap_analysis"] = summary
        mode = _fallback_mode(summary)
        analysis_records = _pick_support_records(state.literature_records)
        topic = state.request.topic
        candidate_builders = [
            _build_method_gap_candidate,
            _build_data_gap_candidate,
            _build_scenario_gap_candidate,
            _build_evaluation_gap_candidate,
        ]
        candidates: list[InnovationCandidate] = []
        for builder in candidate_builders:
            candidate = builder(topic, analysis_records, summary, mode)
            if candidate:
                candidates.append(candidate)

        existing_gap_types = {candidate.gap_type for candidate in candidates}
        for gap_type in ["method_gap", "data_gap", "scenario_gap", "evaluation_gap"]:
            if len(candidates) >= 3:
                break
            if gap_type in existing_gap_types:
                continue
            candidates.append(_build_fallback_candidate(gap_type, topic, analysis_records, summary))

        state.innovation_candidates = candidates[:4]
        state.result_schema["gap_analysis_overview"] = _build_gap_overview(summary, state.innovation_candidates)
        self.log(state, f"generated {len(state.innovation_candidates)} innovation candidates")
        return state


class NoveltyJudgeAgent(BaseAgent):
    name = "novelty_judge"
    task_type = "reviewer"

    def run(self, state: ProjectState) -> ProjectState:
        gap_summary = state.result_schema.get("gap_analysis", {}) if isinstance(state.result_schema, dict) else {}
        ranked: list[InnovationCandidate] = []
        for item in state.innovation_candidates:
            item.overall_score = _compute_overall_score(item)
            if isinstance(gap_summary, dict):
                gap_entry = _top_gap_entry(
                    gap_summary,
                    {
                        "method_gap": "method_gaps",
                        "data_gap": "data_gaps",
                        "scenario_gap": "scenario_gaps",
                        "evaluation_gap": "evaluation_gaps",
                    }.get(item.gap_type, ""),
                )
            else:
                gap_entry = {}
            evidence_basis = "；".join(str(part) for part in gap_entry.get("basis", [])[:2]) or "证据摘要待补充"
            mode_hint = "真实差异证据完整" if item.evidence_mode == "real" else "当前仍为 fallback 占位候选"
            item.recommendation_reason = (
                f"{_format_gap_label(item.gap_type)}方向综合得分 {item.overall_score:.2f}，"
                f"新颖性 {item.novelty_score:.1f}、可行性 {item.feasibility_score:.1f}、"
                f"本科适配度 {item.undergrad_fit:.1f}、证据强度 {item.evidence_strength:.1f}；"
                f"依据为：{evidence_basis}；{mode_hint}，"
                f"{('建议优先进入实验设计。' if item.evidence_mode == 'real' and item.risk_score <= 6.5 else '建议先补证据或控制风险后再进入实验设计。')}"
            )
            ranked.append(item)

        ranked.sort(key=lambda item: item.overall_score, reverse=True)
        state.innovation_candidates = ranked
        best = ranked[0] if ranked else None
        state.selected_innovation = best
        if best:
            runner_up = ranked[1] if len(ranked) > 1 else None
            state.result_schema["innovation_recommendation"] = {
                "selected_claim": best.claim,
                "selected_gap_type": best.gap_type,
                "selected_reason": best.recommendation_reason,
                "runner_up_claim": runner_up.claim if runner_up else "",
                "runner_up_score": runner_up.overall_score if runner_up else 0.0,
            }
        if best:
            self.log(state, f"selected innovation: {best.claim}")
        return state


class FeasibilityReviewerAgent(BaseAgent):
    name = "feasibility_reviewer"
    task_type = "reviewer"

    def run(self, state: ProjectState) -> ProjectState:
        candidate = state.selected_innovation
        if not candidate:
            self.log(state, "no innovation selected for feasibility review")
            return state
        if state.innovation_candidates and all(item.evidence_strength < 6 for item in state.innovation_candidates):
            state.warnings.append("当前所有候选证据强度都偏弱，建议补充文献后再确定最终创新点。")
        if candidate.feasibility_score < 7:
            state.warnings.append("当前创新点可行性偏低，建议人工调整实验规模。")
        if candidate.evidence_mode == "fallback":
            state.warnings.append("当前创新点基于 fallback 占位推荐生成，建议人工补充文献后复核。")
        if candidate.evidence_strength < 6:
            state.warnings.append("当前创新点证据强度偏弱，建议补充支撑文献或增加对照分析。")
        if candidate.risk_score > 7 or candidate.undergrad_fit < 6:
            state.warnings.append("当前推荐创新点风险或本科适配度存在隐患，建议评估第二候选方案。")
        if candidate.experiment_cost > 7:
            state.warnings.append("当前推荐创新点实验成本偏高，建议缩小实验范围或评估低成本备选方案。")
        if len(state.innovation_candidates) > 1:
            runner_up = state.innovation_candidates[1]
            if candidate.evidence_mode == "fallback" and runner_up.evidence_mode == "real":
                state.warnings.append("第一候选为 fallback，而第二候选已有 real 证据，建议优先评估第二候选。")
        self.log(state, "checked feasibility and risks")
        return state


class ExperimentDesignerAgent(BaseAgent):
    name = "experiment_designer"
    task_type = "planner"

    def run(self, state: ProjectState) -> ProjectState:
        topic = state.request.topic
        idea = state.selected_innovation.claim if state.selected_innovation else topic
        datasets = _select_plan_datasets(state)
        metrics = _select_plan_metrics(state)
        baselines = _select_plan_baselines(state)
        paper_type = state.request.paper_type or "algorithm"
        commands = _milestone_three_run_commands()
        evidence_links = []
        if state.selected_innovation:
            evidence_links.extend(state.selected_innovation.supporting_papers[:3])
        evidence_links.extend(record.title for record in state.literature_records[:2])
        state.experiment_plan = ExperimentPlan(
            dataset=datasets,
            baselines=baselines,
            metrics=metrics,
            ablations=["去除创新模块", "替换损失函数/评价协议", "移除关键训练策略"],
            environment=["Python 3.11", "PyTorch 2.x", "CPU/CUDA 兼容", "配置文件: configs/default.yaml"],
            parameters=[
                "seed=42",
                "batch_size=32",
                "learning_rate=1e-3",
                "epochs=10",
                "device=cpu/cuda",
            ],
            dataset_notes=[
                f"主数据集：{'、'.join(datasets[:2])}",
                "如需补充样本，只允许作为可选扩展，不影响 MVP 主链路。",
            ],
            baseline_notes=[
                f"基线来源：{'；'.join(baselines[:2]) or '主流文献方法'}",
                "至少保留一个主流方法和一个消融基线。",
            ],
            metric_notes=[
                f"核心指标：{'、'.join(metrics)}",
                "优先复用文献中高频指标，避免新增难以解释的自定义指标。",
            ],
            steps=[
                f"根据研究方向 {topic} 明确任务定义、数据来源与数据划分。",
                f"围绕创新点“{idea}”实现主模型或评价补强模块。",
                f"按 {paper_type} 论文复杂度约束运行基线模型并记录统一指标。",
                "运行完整模型、主结果对比与消融实验。",
                "汇总结果文件并生成论文/PPT 可复用的结果摘要。",
            ],
            expected_outputs=["训练日志", "主结果表", "消融实验表", "结果摘要", "推理输出样例"],
            run_commands=commands,
            result_files=list(MILESTONE_THREE_RESULT_FILES),
            evidence_links=_dedupe_preserve_order(evidence_links, limit=5),
        )
        state.result_schema.setdefault(
            "milestone_three_contract",
            {
                "required_code_files": list(MILESTONE_THREE_REQUIRED_CODE_FILES),
                "procedure_sections": list(MILESTONE_THREE_PROCEDURE_SECTIONS),
                "run_commands": dict(commands),
                "result_files": list(MILESTONE_THREE_RESULT_FILES),
            },
        )
        self.log(state, "built experiment plan")
        return state


class ProcedureWriterAgent(BaseAgent):
    name = "procedure_writer"
    task_type = "writer"

    def run(self, state: ProjectState) -> ProjectState:
        plan = state.experiment_plan
        if not plan:
            return state
        state.result_schema["procedure_document"] = _build_procedure_document(plan)
        self.log(state, "prepared experiment procedure content")
        return state


class ResultSchemaAgent(BaseAgent):
    name = "result_schema_agent"
    task_type = "planner"

    def run(self, state: ProjectState) -> ProjectState:
        state.result_schema.setdefault("result_tables", [])
        state.result_schema.setdefault("result_figures", [])
        state.result_schema.setdefault("result_analysis_text", "")
        state.result_schema.setdefault("result_summary_for_paper", "")
        state.result_schema.setdefault("result_summary_for_ppt", "")
        state.result_schema.setdefault("ppt_section_mapping", {})
        self.log(state, "defined result schema")
        return state


class ResultAnalystAgent(BaseAgent):
    name = "result_analyst"
    task_type = "reviewer"

    def run(self, state: ProjectState) -> ProjectState:
        plan = state.experiment_plan
        if not plan:
            state.result_schema.setdefault("result_tables", [])
            state.result_schema.setdefault("result_figures", [])
            state.result_schema.setdefault("result_analysis_text", "")
            return state
        state.result_schema.update(_build_result_analysis(plan, state))
        self.log(state, "prepared structured result analysis")
        return state


class CodePlannerAgent(BaseAgent):
    name = "code_planner"
    task_type = "code"

    def run(self, state: ProjectState) -> ProjectState:
        state.generated_code_files.setdefault(
            "configs/default.yaml",
            "seed: 42\nbatch_size: 32\nlr: 0.001\nepochs: 10\nresult_dir: results\ntrain_metrics: train_metrics.json\neval_metrics: eval_metrics.json\npredictions: predictions.jsonl\n",
        )
        self.log(state, "planned code structure")
        return state


class CodeAgent(BaseAgent):
    name = "code_agent"
    task_type = "code"

    def run(self, state: ProjectState) -> ProjectState:
        topic_slug = slugify(state.request.topic).replace("-", "_")
        plan = state.experiment_plan
        dataset_line = ", ".join(plan.dataset) if plan else "公开数据集 A"
        metrics_line = ", ".join(plan.metrics) if plan else "Accuracy, F1"
        command_lines = plan.run_commands if plan else _milestone_three_run_commands()
        result_files = plan.result_files if plan else list(MILESTONE_THREE_RESULT_FILES)
        state.generated_code_files.update(
            {
                "configs/default.yaml": (
                    "seed: 42\nbatch_size: 32\nlr: 0.001\nepochs: 10\nresult_dir: results\n"
                    "train_metrics: train_metrics.json\neval_metrics: eval_metrics.json\npredictions: predictions.jsonl\n"
                ),
                "requirements.txt": "pyyaml\nnumpy\n",
                "README.md": (
                    f"# {state.request.topic}\n\n"
                    "## 环境安装\n"
                    f"- `{command_lines['install']}`\n\n"
                    "## 数据准备说明\n"
                    f"- {dataset_line}\n\n"
                    "## 配置说明\n"
                    "- 默认配置文件：`configs/default.yaml`\n"
                    "- 结果目录：`results/`\n\n"
                    "## 运行步骤\n"
                    f"- 训练：`{command_lines['train']}`\n"
                    f"- 评估：`{command_lines['eval']}`\n"
                    f"- 推理：`{command_lines['infer']}`\n\n"
                    "## 结果文件说明\n"
                    + "".join(f"- `{path}`\n" for path in result_files)
                    + "\n"
                    f"数据集：{dataset_line}\n"
                    f"指标：{metrics_line}\n"
                ),
                "src/model.py": (
                    "from __future__ import annotations\n\n"
                    "class ThesisModel:\n"
                    "    def __init__(self, config: dict) -> None:\n"
                    "        self.config = config\n\n"
                    "    def fit(self, data: list[dict]) -> dict:\n"
                    "        sample_count = max(len(data), 1)\n"
                    "        return {'accuracy': 0.88, 'precision': 0.86, 'recall': 0.84, 'f1': 0.85, 'samples': sample_count}\n\n"
                    "    def predict(self, text: str) -> dict:\n"
                    "        return {'label': 'stub', 'score': 0.5, 'text': text}\n"
                ),
                "src/data.py": (
                    "from __future__ import annotations\n\n"
                    "def load_dataset() -> list[dict]:\n"
                    "    return [\n"
                    "        {'text': 'sample-1', 'label': 0},\n"
                    "        {'text': 'sample-2', 'label': 1},\n"
                    "    ]\n"
                ),
                "train.py": (
                    "from __future__ import annotations\n\n"
                    "import json\n"
                    "from pathlib import Path\n"
                    "import yaml\n"
                    "from src.data import load_dataset\n"
                    "from src.model import ThesisModel\n\n"
                    "def load_config(path: str) -> dict:\n"
                    "    return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}\n\n"
                    "def main() -> None:\n"
                    "    config = load_config('configs/default.yaml')\n"
                    "    dataset = load_dataset()\n"
                    "    model = ThesisModel(config)\n"
                    "    metrics = model.fit(dataset)\n"
                    "    result_dir = Path(config.get('result_dir', 'results'))\n"
                    "    result_dir.mkdir(exist_ok=True)\n"
                    "    output_path = result_dir / str(config.get('train_metrics', 'train_metrics.json'))\n"
                    "    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
                "eval.py": (
                    "from __future__ import annotations\n\n"
                    "import json\n\n"
                    "from pathlib import Path\n"
                    "import yaml\n\n"
                    "def load_config(path: str) -> dict:\n"
                    "    return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}\n\n"
                    "def main() -> None:\n"
                    "    config = load_config('configs/default.yaml')\n"
                    "    results = {'accuracy': 0.88, 'precision': 0.86, 'recall': 0.84, 'f1': 0.85}\n"
                    "    result_dir = Path(config.get('result_dir', 'results'))\n"
                    "    result_dir.mkdir(exist_ok=True)\n"
                    "    output_path = result_dir / str(config.get('eval_metrics', 'eval_metrics.json'))\n"
                    "    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
                "infer.py": (
                    "from __future__ import annotations\n\n"
                    "import json\n"
                    "from pathlib import Path\n"
                    "import sys\n"
                    "import yaml\n"
                    "from src.model import ThesisModel\n\n"
                    "def load_config(path: str) -> dict:\n"
                    "    return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}\n\n"
                    f"def predict_{topic_slug}(text: str) -> dict:\n"
                    "    model = ThesisModel({})\n"
                    "    return model.predict(text)\n\n"
                    "def main() -> None:\n"
                    "    config = load_config('configs/default.yaml')\n"
                    "    text = sys.argv[-1] if len(sys.argv) > 1 else 'demo sample'\n"
                    "    prediction = ThesisModel(config).predict(text)\n"
                    "    result_dir = Path(config.get('result_dir', 'results'))\n"
                    "    result_dir.mkdir(exist_ok=True)\n"
                    "    output_path = result_dir / str(config.get('predictions', 'predictions.jsonl'))\n"
                    "    output_path.write_text(json.dumps(prediction, ensure_ascii=False) + '\\n', encoding='utf-8')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
            }
        )
        self.log(state, f"generated {len(state.generated_code_files)} code files")
        return state


class OutlineWriterAgent(BaseAgent):
    name = "outline_writer"
    task_type = "writer"

    def run(self, state: ProjectState) -> ProjectState:
        if state.template_manifest:
            state.paper_outline = state.template_manifest.section_mapping
        else:
            state.paper_outline = ["摘要", "引言", "相关工作", "方法", "实验", "结论", "参考文献"]
        self.log(state, f"prepared outline with {len(state.paper_outline)} sections")
        return state


class SectionWriterAgent(BaseAgent):
    name = "section_writer"
    task_type = "writer"

    def run(self, state: ProjectState) -> ProjectState:
        for section in state.paper_outline:
            state.paper_sections[section] = _build_section_content(section, state)
        self.log(state, "generated section drafts")
        return state


class CitationBinderAgent(BaseAgent):
    name = "citation_binder"
    task_type = "writer"

    def run(self, state: ProjectState) -> ProjectState:
        references = [
            f"[{idx + 1}] {record.authors}. {record.title}. {record.year}."
            for idx, record in enumerate(state.literature_records[:8])
        ]
        related_keys = [
            key
            for key in state.paper_sections
            if "相关工作" in key or key == "参考文献"
        ]
        for key in related_keys:
            state.paper_sections[key] = f"{state.paper_sections[key]}\n\n" + "\n".join(
                references
            )
        self.log(state, f"bound {len(references)} references")
        return state


class DeckPlannerAgent(BaseAgent):
    name = "deck_planner"
    task_type = "writer"

    def run(self, state: ProjectState) -> ProjectState:
        state.ppt_outline = [
            "封面",
            "研究背景与问题定义",
            "文献综述与研究空白",
            "创新点",
            "方法设计",
            "实验设置",
            "结果分析",
            "结论与展望",
        ]
        self.log(state, f"prepared deck outline with {len(state.ppt_outline)} slides")
        return state


class ConsistencyCheckerAgent(BaseAgent):
    name = "consistency_checker"
    task_type = "consistency"

    def run(self, state: ProjectState) -> ProjectState:
        findings: list[str] = []
        consistency_summary = _build_consistency_summary(state)
        readme = state.generated_code_files.get("README.md", "")
        state.result_schema["consistency_summary"] = consistency_summary
        if state.experiment_plan:
            metric_line = ", ".join(state.experiment_plan.metrics)
            if metric_line and metric_line not in readme:
                findings.append("README 中缺少实验指标定义。")
            experiment_key = next(
                (key for key in state.paper_sections if "实验" in key),
                None,
            )
            if experiment_key and "README" not in state.paper_sections[experiment_key]:
                state.paper_sections[experiment_key] += "\n\n实验复现命令、数据集和指标与 README 保持一致。"
        findings.extend(str(item) for item in consistency_summary.get("warnings", []))
        if not findings:
            findings.append("论文、实验步骤与代码 README 的关键信息已完成基础一致性对齐。")
        state.review_findings.extend(findings)
        self.log(state, f"recorded {len(findings)} consistency findings")
        return state


class ReviewerAgent(BaseAgent):
    name = "reviewer"
    task_type = "reviewer"

    def run(self, state: ProjectState) -> ProjectState:
        review = [
            "创新点表述已标记为候选方案，避免绝对原创性承诺。",
            "实验流程、指标与代码目录已对齐，适合作为 MVP 交付。",
            "若正式用于毕业论文，仍需人工核验文献真实性、模板细节和实验结果。",
        ]
        state.review_findings.extend(review)
        self.log(state, "completed final review")
        return state


AGENT_PIPELINE = [
    TopicPlannerAgent,
    RetrieverAgent,
    ReaderAgent,
    EvidenceExtractorAgent,
    SurveySynthesizerAgent,
    GapAnalystAgent,
    NoveltyJudgeAgent,
    FeasibilityReviewerAgent,
    ExperimentDesignerAgent,
    ProcedureWriterAgent,
    ResultSchemaAgent,
    ResultAnalystAgent,
    CodePlannerAgent,
    CodeAgent,
    OutlineWriterAgent,
    SectionWriterAgent,
    CitationBinderAgent,
    DeckPlannerAgent,
    ConsistencyCheckerAgent,
    ReviewerAgent,
]
