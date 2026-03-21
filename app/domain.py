from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ProjectStatus = Literal["created", "running", "completed", "failed"]
WorkflowPhase = Literal[
    "intake",
    "planning",
    "research",
    "implementation",
    "writing_delivery",
    "review",
    "completed",
]
WorkflowNodeStatus = Literal["pending", "running", "succeeded", "failed", "skipped", "rolled_back"]
WorkflowOutcome = Literal["not_started", "success", "partial_success", "rollback_success", "failed"]
FailureCategory = Literal["transient", "validation", "consistency", "rendering", "unknown"]
AuditEventLevel = Literal["info", "warning", "error"]
TemplateSourceType = Literal["user_upload", "library_default"]
EvidenceSourceType = Literal["abstract", "pdf", "manual", "fallback"]
PdfParseStatus = Literal["not_applicable", "success", "degraded", "failed"]
RetrievalStatus = Literal["success", "partial", "fallback"]
GapType = Literal["method_gap", "data_gap", "scenario_gap", "evaluation_gap"]
InnovationEvidenceMode = Literal["real", "fallback"]
DeliveryMode = Literal["draft", "final"]
MODEL_TASK_TYPES = (
    "planner",
    "reviewer",
    "consistency",
    "survey_synthesizer",
    "writer",
    "code",
)
MODEL_PROVIDER_TEST_TASK_ORDER = (
    "planner",
    "writer",
    "reviewer",
    "consistency",
    "survey_synthesizer",
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
    delivery_mode: DeliveryMode = "draft"


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
class ModelProviderTestPayload:
    provider: ModelProviderSettings


@dataclass(slots=True)
class ModelProviderTestResult:
    ok: bool
    provider: str
    model: str
    message: str
    response_preview: str | None = None


@dataclass(slots=True)
class TemplateSource:
    source_type: TemplateSourceType
    template_id: str
    template_name: str
    manifest_version: str = "1.0"
    template_path: str | None = None
    ppt_template_path: str | None = None


@dataclass(slots=True)
class TemplateManifest:
    # Template-observed section labels and placeholders used for style/template compatibility.
    # They are not the authoritative source of thesis body structure.
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
class RetrievalSummary:
    retrieval_status: RetrievalStatus = "fallback"
    valid_paper_count: int = 0
    fallback_count: int = 0
    failed_sources: list[str] = field(default_factory=list)
    needs_review_count: int = 0


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
    citation_count: int = 0
    retrieval_rank: int = 0
    is_fallback: bool = False
    problem: str = ""
    method: str = ""
    dataset: str = ""
    metrics: str = ""
    conclusion: str = ""
    limitations: str = ""
    evidence_source: EvidenceSourceType = "abstract"
    confidence_score: float = 0.0
    evidence_quote: str = ""
    pdf_parse_status: PdfParseStatus = "not_applicable"
    pdf_parse_message: str = ""
    needs_review: bool = False
    review_note: str = ""


@dataclass(slots=True)
class InnovationCandidate:
    claim: str
    supporting_papers: list[str]
    contrast_papers: list[str]
    novelty_reason: str
    feasibility_score: float
    risk: str
    verification_plan: str
    analysis_basis: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    contrast_evidence: list[str] = field(default_factory=list)
    gap_type: GapType = "method_gap"
    rare_reason: str = ""
    recommendation_reason: str = ""
    novelty_score: float = 0.0
    risk_score: float = 0.0
    experiment_cost: float = 0.0
    undergrad_fit: float = 0.0
    evidence_strength: float = 0.0
    evidence_mode: InnovationEvidenceMode = "fallback"
    overall_score: float = 0.0


@dataclass(slots=True)
class ExperimentPlan:
    dataset: list[str]
    baselines: list[str]
    metrics: list[str]
    ablations: list[str]
    environment: list[str]
    steps: list[str]
    expected_outputs: list[str]
    parameters: list[str] = field(default_factory=list)
    dataset_notes: list[str] = field(default_factory=list)
    baseline_notes: list[str] = field(default_factory=list)
    metric_notes: list[str] = field(default_factory=list)
    run_commands: dict[str, str] = field(default_factory=dict)
    result_files: list[str] = field(default_factory=list)
    evidence_links: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PaperNode:
    title: str
    level: int
    paragraphs: list[str] = field(default_factory=list)
    children: list["PaperNode"] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    status: str = "generated"


@dataclass(slots=True)
class PaperDocument:
    title: str
    nodes: list[PaperNode] = field(default_factory=list)


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
class WorkflowNodeRun:
    node_name: str
    phase: WorkflowPhase
    status: WorkflowNodeStatus = "pending"
    attempt: int = 0
    started_at: str = ""
    ended_at: str = ""
    provider: str = ""
    model: str = ""
    fallback_used: bool = False
    message: str = ""
    error_category: FailureCategory = "unknown"
    error_detail: str = ""


@dataclass(slots=True)
class AuditEvent:
    timestamp: str
    level: AuditEventLevel
    phase: WorkflowPhase
    node_name: str
    message: str
    attempt: int = 0
    provider: str = ""
    model: str = ""
    fallback_used: bool = False


@dataclass(slots=True)
class WorkflowCheckpoint:
    checkpoint_id: str
    phase: WorkflowPhase
    node_name: str
    created_at: str
    summary: str = ""


@dataclass(slots=True)
class RollbackRecord:
    from_phase: WorkflowPhase
    to_phase: WorkflowPhase
    reason: str
    trigger_node: str
    created_at: str
    recovered: bool = False


@dataclass(slots=True)
class ProjectState:
    project_id: str
    request: ProjectCreate
    status: ProjectStatus = "created"
    workflow_phase: WorkflowPhase = "intake"
    workflow_outcome: WorkflowOutcome = "not_started"
    current_node: str = ""
    active_run_id: str = ""
    last_error: str = ""
    last_failure_category: FailureCategory = "unknown"
    template_source: TemplateSource | None = None
    template_manifest: TemplateManifest | None = None
    uploaded_pdf_paths: list[str] = field(default_factory=list)
    literature_records: list[LiteratureRecord] = field(default_factory=list)
    retrieval_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    retrieval_summary: RetrievalSummary = field(default_factory=RetrievalSummary)
    survey_table: list[dict[str, Any]] = field(default_factory=list)
    literature_detail_fields: list[str] = field(default_factory=list)
    innovation_candidates: list[InnovationCandidate] = field(default_factory=list)
    selected_innovation: InnovationCandidate | None = None
    experiment_plan: ExperimentPlan | None = None
    result_schema: dict[str, Any] = field(default_factory=dict)
    generated_code_files: dict[str, str] = field(default_factory=dict)
    paper_outline: list[str] = field(default_factory=list)
    paper_sections: dict[str, str] = field(default_factory=dict)
    paper_document: PaperDocument | None = None
    ppt_outline: list[str] = field(default_factory=list)
    review_findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: ArtifactBundle = field(default_factory=ArtifactBundle)
    execution_log: list[str] = field(default_factory=list)
    node_runs: dict[str, WorkflowNodeRun] = field(default_factory=dict)
    audit_trail: list[AuditEvent] = field(default_factory=list)
    checkpoints: list[WorkflowCheckpoint] = field(default_factory=list)
    rollback_history: list[RollbackRecord] = field(default_factory=list)
