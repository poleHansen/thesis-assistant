from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ProjectStatus = Literal["created", "running", "completed", "failed"]
TemplateSourceType = Literal["user_upload", "library_default"]
MODEL_TASK_TYPES = (
    "planner",
    "reviewer",
    "consistency",
    "survey_synthesizer",
    "writer",
    "code",
)


@dataclass(slots=True)
class ProjectCreate:
    topic: str
    constraints: list[str] = field(default_factory=list)
    paper_type: str = "algorithm"
    language: str = "zh-CN"
    need_code: bool = True
    need_ppt: bool = True
    school_requirements: str = ""


@dataclass(slots=True)
class ProviderConfig:
    provider: str
    api_base: str
    api_key_env: str
    model_aliases: dict[str, str]
    max_context: int = 32768
    supports_json_mode: bool = True
    supports_embedding: bool = True
    priority: int = 10


@dataclass(slots=True)
class ModelRoutingPolicy:
    task_type: str
    primary_model: str
    fallback_models: list[str]
    temperature: float = 0.2
    max_tokens: int = 4096


@dataclass(slots=True)
class ModelProviderSettings:
    id: str
    label: str
    api_base: str
    api_key: str
    priority: int
    enabled: bool
    models: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ModelSettingsPayload:
    providers: list[ModelProviderSettings] = field(default_factory=list)
    task_routes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TemplateSource:
    source_type: TemplateSourceType
    template_id: str
    template_name: str
    manifest_version: str = "1.0"
    template_path: str | None = None


@dataclass(slots=True)
class TemplateManifest:
    section_mapping: list[str]
    style_mapping: dict[str, str]
    cover_fields: list[str]
    figure_slots: list[str]
    table_slots: list[str]
    citation_style: str
    header_footer_rules: dict[str, str]
    toc_rules: dict[str, Any]
    ppt_layouts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LiteratureRecord:
    source: str
    title: str
    authors: str
    year: int
    abstract: str
    doi_or_url: str
    pdf_path: str | None = None
    evidence_spans: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InnovationCandidate:
    claim: str
    supporting_papers: list[str]
    contrast_papers: list[str]
    novelty_reason: str
    feasibility_score: float
    risk: str
    verification_plan: str


@dataclass(slots=True)
class ExperimentPlan:
    dataset: list[str]
    baselines: list[str]
    metrics: list[str]
    ablations: list[str]
    environment: list[str]
    steps: list[str]
    expected_outputs: list[str]


@dataclass(slots=True)
class ArtifactBundle:
    literature_review: str | None = None
    innovation_report: str | None = None
    experiment_plan: str | None = None
    procedure: str | None = None
    thesis_docx: str | None = None
    thesis_pdf: str | None = None
    code_zip: str | None = None
    defense_pptx: str | None = None
    qa_report: str | None = None


@dataclass(slots=True)
class ProjectState:
    project_id: str
    request: ProjectCreate
    status: ProjectStatus = "created"
    template_source: TemplateSource | None = None
    template_manifest: TemplateManifest | None = None
    uploaded_pdf_paths: list[str] = field(default_factory=list)
    literature_records: list[LiteratureRecord] = field(default_factory=list)
    survey_table: list[dict[str, Any]] = field(default_factory=list)
    innovation_candidates: list[InnovationCandidate] = field(default_factory=list)
    selected_innovation: InnovationCandidate | None = None
    experiment_plan: ExperimentPlan | None = None
    result_schema: dict[str, Any] = field(default_factory=dict)
    generated_code_files: dict[str, str] = field(default_factory=dict)
    paper_outline: list[str] = field(default_factory=list)
    paper_sections: dict[str, str] = field(default_factory=dict)
    ppt_outline: list[str] = field(default_factory=list)
    review_findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: ArtifactBundle = field(default_factory=ArtifactBundle)
    execution_log: list[str] = field(default_factory=list)
