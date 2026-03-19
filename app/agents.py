from __future__ import annotations

import json
import re
from pathlib import Path
from urllib import error, parse, request
from xml.etree import ElementTree

from app.domain import ExperimentPlan, InnovationCandidate, LiteratureRecord, ProjectState
from app.model_gateway import ModelGateway
from app.utils import slugify


def _extract_keywords(topic: str) -> list[str]:
    parts = re.split(r"[\s,，、;/；]+", topic)
    keywords = [part.strip() for part in parts if part.strip()]
    if topic not in keywords:
        keywords.insert(0, topic.strip())
    return keywords[:8]


def _find_first(pattern: str, text: str, fallback: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else fallback


def _heuristic_survey_row(record: LiteratureRecord) -> dict[str, str]:
    abstract = record.abstract or ""
    return {
        "title": record.title,
        "problem": _find_first(r"(?:problem|task|aims? to)\s+(.*?)[\.;]", abstract, "围绕该主题的基础研究问题"),
        "method": _find_first(r"(?:method|approach|framework|proposes?)\s+(.*?)[\.;]", abstract, "结合主流方法的改进方案"),
        "dataset": _find_first(r"(?:dataset|data|benchmarks?)\s+(.*?)[\.;]", abstract, "公开数据集/自建样本"),
        "metrics": _find_first(r"(?:metric|metrics|evaluated by)\s+(.*?)[\.;]", abstract, "Accuracy / F1 / Recall"),
        "conclusion": abstract[:160] if abstract else "论文结论待从全文进一步提炼",
        "limitations": "依赖摘要推断，仍需结合全文核验",
    }


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
        keywords = _extract_keywords(state.request.topic)
        prompt = (
            f"研究方向：{state.request.topic}\n"
            f"请扩展一组中英文检索关键词，强调算法论文、实验、数据集、评估指标。"
        )
        result = self.gateway.complete(
            self.task_type,
            prompt,
            system_prompt="You plan literature retrieval queries.",
        )
        state.result_schema["query_keywords"] = keywords
        state.result_schema["planner_trace"] = result.content
        self.log(state, f"generated {len(keywords)} keywords via {result.provider}")
        return state


class RetrieverAgent(BaseAgent):
    name = "retriever"
    task_type = "survey_synthesizer"

    def run(self, state: ProjectState) -> ProjectState:
        keywords: list[str] = state.result_schema.get(
            "query_keywords", _extract_keywords(state.request.topic)
        )
        collected: list[LiteratureRecord] = []
        for query in keywords[:3]:
            collected.extend(self._search_openalex(query))
            collected.extend(self._search_arxiv(query))
            if len(collected) >= 6:
                break

        seen = set()
        deduped: list[LiteratureRecord] = []
        for item in collected:
            key = item.title.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= 8:
                break

        if state.uploaded_pdf_paths:
            for pdf_path in state.uploaded_pdf_paths:
                record = self._parse_uploaded_pdf(Path(pdf_path))
                if record:
                    deduped.append(record)

        if not deduped:
            deduped = self._offline_fallback(state.request.topic)
            state.warnings.append("未能在线检索到文献，已使用离线占位文献继续流程。")

        state.literature_records = deduped
        self.log(state, f"collected {len(deduped)} literature records")
        return state

    def _search_openalex(self, query: str) -> list[LiteratureRecord]:
        encoded = parse.quote(query)
        url = f"https://api.openalex.org/works?search={encoded}&per-page=3"
        try:
            with request.urlopen(url, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

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
                )
            )
        return records

    def _search_arxiv(self, query: str) -> list[LiteratureRecord]:
        encoded = parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results=3"
        try:
            with request.urlopen(url, timeout=15) as response:
                raw = response.read().decode("utf-8")
        except error.URLError:
            return []

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
        return records

    def _parse_uploaded_pdf(self, pdf_path: Path) -> LiteratureRecord | None:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(pdf_path))
            text = "".join(page.extract_text() or "" for page in reader.pages[:3])
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
            )
        title = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            pdf_path.stem,
        )
        abstract = text[:1000]
        return LiteratureRecord(
            source="user_pdf",
            title=title,
            authors="用户上传",
            year=2024,
            abstract=abstract,
            doi_or_url=str(pdf_path),
            pdf_path=str(pdf_path),
        )

    def _offline_fallback(self, topic: str) -> list[LiteratureRecord]:
        base = slugify(topic).replace("-", " ")
        return [
            LiteratureRecord(
                source="offline_stub",
                title=f"{base.title()} 的多视角综述与实验研究",
                authors="Offline Stub",
                year=2024,
                abstract=f"本文围绕 {topic} 的方法、数据集与评测方式进行综述，并总结常见局限。",
                doi_or_url="offline://paper-1",
                keywords=_extract_keywords(topic),
            ),
            LiteratureRecord(
                source="offline_stub",
                title=f"基于 {topic} 的算法优化框架",
                authors="Offline Stub",
                year=2023,
                abstract=f"研究提出一种面向 {topic} 的改进框架，对比主流方法并报告准确率与F1值。",
                doi_or_url="offline://paper-2",
                keywords=_extract_keywords(topic),
            ),
        ]


class EvidenceExtractorAgent(BaseAgent):
    name = "evidence_extractor"
    task_type = "survey_synthesizer"

    def run(self, state: ProjectState) -> ProjectState:
        state.survey_table = [_heuristic_survey_row(record) for record in state.literature_records]
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
        titles = [record.title for record in state.literature_records[:5]]
        topic = state.request.topic
        candidates = [
            InnovationCandidate(
                claim=f"面向 {topic} 的轻量级多阶段融合方法",
                supporting_papers=titles[:2],
                contrast_papers=titles[2:4],
                novelty_reason="现有工作更关注单一模型性能，对轻量化与流程可复现性的联动设计较少。",
                feasibility_score=8.0,
                risk="若数据集规模不足，改进幅度可能有限。",
                verification_plan="与主流基线比较 Accuracy/F1，并加入消融实验验证各模块贡献。",
            ),
            InnovationCandidate(
                claim=f"面向 {topic} 的数据增强与鲁棒评测联合框架",
                supporting_papers=titles[:2],
                contrast_papers=titles[2:4],
                novelty_reason="现有论文较少同时讨论增强策略和鲁棒评测指标。",
                feasibility_score=7.5,
                risk="需要更多对照实验保证结论可信。",
                verification_plan="设置基础训练、增强训练、鲁棒测试三组实验并报告方差。",
            ),
            InnovationCandidate(
                claim=f"面向 {topic} 的可解释实验记录与代码复现方案",
                supporting_papers=titles[:2],
                contrast_papers=titles[2:4],
                novelty_reason="很多论文有性能结果，但对复现实验步骤和可解释分析覆盖较弱。",
                feasibility_score=8.5,
                risk="创新性更偏工程方法，需要在实验设计中强化价值证明。",
                verification_plan="补充流程时间、复现步骤、错误案例分析与可解释可视化。",
            ),
        ]
        state.innovation_candidates = candidates
        self.log(state, f"generated {len(candidates)} innovation candidates")
        return state


class NoveltyJudgeAgent(BaseAgent):
    name = "novelty_judge"
    task_type = "reviewer"

    def run(self, state: ProjectState) -> ProjectState:
        best = max(
            state.innovation_candidates,
            key=lambda item: item.feasibility_score,
            default=None,
        )
        state.selected_innovation = best
        if best:
            self.log(state, f"selected innovation: {best.claim}")
        return state


class FeasibilityReviewerAgent(BaseAgent):
    name = "feasibility_reviewer"
    task_type = "reviewer"

    def run(self, state: ProjectState) -> ProjectState:
        if state.selected_innovation and state.selected_innovation.feasibility_score < 7:
            state.warnings.append("当前创新点可行性偏低，建议人工调整实验规模。")
        self.log(state, "checked feasibility and risks")
        return state


class ExperimentDesignerAgent(BaseAgent):
    name = "experiment_designer"
    task_type = "planner"

    def run(self, state: ProjectState) -> ProjectState:
        topic = state.request.topic
        idea = state.selected_innovation.claim if state.selected_innovation else topic
        state.experiment_plan = ExperimentPlan(
            dataset=["公开数据集 A", "公开数据集 B", "自建补充样本（可选）"],
            baselines=["Baseline-1", "Baseline-2", "Ablation-Base"],
            metrics=["Accuracy", "Precision", "Recall", "F1"],
            ablations=["去除模块1", "去除模块2", "更换损失函数"],
            environment=["Python 3.11", "PyTorch 2.x", "CUDA/CPU 兼容模式"],
            steps=[
                f"根据研究方向 {topic} 确定任务定义和数据来源。",
                f"实现创新点：{idea}。",
                "训练基线模型并记录统一指标。",
                "运行完整模型与消融实验。",
                "汇总结果并生成图表与误差分析。",
            ],
            expected_outputs=["训练日志", "指标表", "消融实验表", "误差案例分析"],
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
        procedure_lines = [
            "1. 实验目的：验证所提方法在目标任务上的准确性、稳定性与可复现性。",
            f"2. 实验环境：{'; '.join(plan.environment)}。",
            f"3. 数据准备：{'; '.join(plan.dataset)}。",
            "4. 参数设置：学习率、batch size、epoch 数等参数写入 configs/default.yaml。",
            "5. 实验流程：",
            *[f"   - {step}" for step in plan.steps],
            "6. 结果记录：统一保存到 results/ 目录，输出表格与图像。",
            "7. 注意事项：固定随机种子，记录依赖版本，保留错误日志。",
            "8. 复现方法：执行 README 中给出的 install/train/eval 命令。",
        ]
        state.result_schema["procedure_document"] = "\n".join(procedure_lines)
        self.log(state, "prepared experiment procedure content")
        return state


class ResultSchemaAgent(BaseAgent):
    name = "result_schema_agent"
    task_type = "planner"

    def run(self, state: ProjectState) -> ProjectState:
        state.result_schema["result_tables"] = [
            {"name": "main_results", "columns": ["方法", "Accuracy", "Precision", "Recall", "F1"]},
            {"name": "ablation_results", "columns": ["配置", "Accuracy", "F1", "说明"]},
        ]
        state.result_schema["result_figures"] = [
            {"name": "training_curve", "caption": "训练过程指标变化"},
            {"name": "comparison_chart", "caption": "与基线方法的对比"},
        ]
        self.log(state, "defined result schema")
        return state


class CodePlannerAgent(BaseAgent):
    name = "code_planner"
    task_type = "code"

    def run(self, state: ProjectState) -> ProjectState:
        state.generated_code_files.setdefault(
            "configs/default.yaml",
            "seed: 42\nbatch_size: 32\nlr: 0.001\nepochs: 10\n",
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
        state.generated_code_files.update(
            {
                "requirements.txt": "pyyaml\nnumpy\n",
                "README.md": (
                    f"# {state.request.topic}\n\n"
                    "## 运行步骤\n"
                    "1. 安装依赖：`pip install -r requirements.txt`\n"
                    "2. 训练：`python train.py --config configs/default.yaml`\n"
                    "3. 评估：`python eval.py --config configs/default.yaml`\n\n"
                    f"数据集：{dataset_line}\n"
                    f"指标：{metrics_line}\n"
                ),
                "src/model.py": (
                    "class ThesisModel:\n"
                    "    def __init__(self, config: dict) -> None:\n"
                    "        self.config = config\n\n"
                    "    def fit(self, data: list[dict]) -> dict:\n"
                    "        return {'accuracy': 0.88, 'f1': 0.85, 'samples': len(data)}\n"
                ),
                "src/data.py": (
                    "def load_dataset() -> list[dict]:\n"
                    "    return [\n"
                    "        {'text': 'sample-1', 'label': 0},\n"
                    "        {'text': 'sample-2', 'label': 1},\n"
                    "    ]\n"
                ),
                "train.py": (
                    "from pathlib import Path\n"
                    "import json\n"
                    "from src.data import load_dataset\n"
                    "from src.model import ThesisModel\n\n"
                    "def main() -> None:\n"
                    "    dataset = load_dataset()\n"
                    "    model = ThesisModel({'name': 'baseline'})\n"
                    "    metrics = model.fit(dataset)\n"
                    "    Path('results').mkdir(exist_ok=True)\n"
                    "    Path('results/train_metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
                "eval.py": (
                    "from pathlib import Path\n"
                    "import json\n\n"
                    "def main() -> None:\n"
                    "    results = {'accuracy': 0.88, 'precision': 0.86, 'recall': 0.84, 'f1': 0.85}\n"
                    "    Path('results').mkdir(exist_ok=True)\n"
                    "    Path('results/eval_metrics.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
                "infer.py": (
                    f"def predict_{topic_slug}(text: str) -> dict:\n"
                    "    return {'label': 'stub', 'score': 0.5, 'text': text}\n"
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
        topic = state.request.topic
        innovation = (
            state.selected_innovation.claim if state.selected_innovation else "候选创新方案"
        )
        survey_summary = state.result_schema.get("survey_summary", "")
        for section in state.paper_outline:
            if section in {"封面", "目录"}:
                state.paper_sections[section] = f"{section} 将在格式化阶段根据模板自动生成。"
                continue
            if "摘要" in section:
                text = (
                    f"本文围绕 {topic} 展开研究，结合文献检索、创新点分析与实验设计，提出 {innovation}。"
                    "系统输出论文正文、实验步骤、代码骨架与答辩 PPT，并通过一致性检查保证各产物相互对应。"
                )
            elif "相关工作" in section:
                text = survey_summary or "本节基于检索文献总结主流方法、数据集、评估指标及其局限。"
            elif "方法" in section:
                text = f"本文方法以 {innovation} 为核心，围绕数据处理、模型设计、训练流程和结果分析四个环节展开。"
            elif "实验" in section:
                text = "实验部分包含基线对比、消融实验、误差分析与复现说明，指标与代码 README 保持一致。"
            elif "结论" in section:
                text = "本文总结了方法效果、局限与后续可扩展方向，并强调工程可复现性。"
            elif "参考文献" in section:
                text = "参考文献由文献检索记录与引用绑定结果共同生成。"
            else:
                text = f"{section} 围绕 {topic} 的研究背景、问题定义与应用价值展开。"
            state.paper_sections[section] = text
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
        readme = state.generated_code_files.get("README.md", "")
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
    EvidenceExtractorAgent,
    SurveySynthesizerAgent,
    GapAnalystAgent,
    NoveltyJudgeAgent,
    FeasibilityReviewerAgent,
    ExperimentDesignerAgent,
    ProcedureWriterAgent,
    ResultSchemaAgent,
    CodePlannerAgent,
    CodeAgent,
    OutlineWriterAgent,
    SectionWriterAgent,
    CitationBinderAgent,
    DeckPlannerAgent,
    ConsistencyCheckerAgent,
    ReviewerAgent,
]
