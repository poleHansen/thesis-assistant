export type ProjectStatus = "created" | "running" | "completed" | "failed";
export type WorkflowPhase =
  | "intake"
  | "planning"
  | "research"
  | "implementation"
  | "writing_delivery"
  | "review"
  | "completed";
export type WorkflowNodeStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped"
  | "rolled_back";
export type WorkflowOutcome =
  | "not_started"
  | "success"
  | "partial_success"
  | "rollback_success"
  | "failed";
export type FailureCategory =
  | "transient"
  | "validation"
  | "consistency"
  | "rendering"
  | "unknown";
export type TemplateSourceType = "user_upload" | "library_default";
export type UploadKind = "word_template" | "ppt_template" | "paper_pdf";
export type ModelTaskType =
  | "planner"
  | "reviewer"
  | "consistency"
  | "survey_synthesizer"
  | "writer"
  | "code";

export interface ProjectCreate {
  topic: string;
  constraints: string[];
  paper_type: string;
  language: string;
  need_code: boolean;
  need_ppt: boolean;
  school_requirements: string;
  delivery_mode: "draft" | "final";
}

export interface TemplateSource {
  source_type: TemplateSourceType;
  template_id: string;
  template_name: string;
  manifest_version: string;
  template_path?: string | null;
  ppt_template_path?: string | null;
}

export interface TemplateManifest {
  section_mapping: string[];
  style_mapping: Record<string, string>;
  cover_fields: string[];
  figure_slots: string[];
  table_slots: string[];
  citation_style: string;
  header_footer_rules: Record<string, string>;
  toc_rules: Record<string, unknown>;
  ppt_layouts: string[];
}

export interface LiteratureRecord {
  source: string;
  title: string;
  authors: string;
  year: number;
  abstract: string;
  doi_or_url: string;
  pdf_path?: string | null;
  evidence_spans: string[];
  keywords: string[];
  citation_count: number;
  retrieval_rank: number;
  is_fallback: boolean;
  problem: string;
  method: string;
  dataset: string;
  metrics: string;
  conclusion: string;
  limitations: string;
  evidence_source: string;
  confidence_score: number;
  evidence_quote: string;
  pdf_parse_status: string;
  pdf_parse_message: string;
  needs_review: boolean;
  review_note: string;
}

export interface RetrievalDiagnostic {
  source: string;
  query: string;
  original_query?: string;
  query_language?: string;
  ok: boolean;
  count: number;
  error: string;
}

export interface RetrievalSummary {
  retrieval_status: "success" | "partial" | "fallback";
  valid_paper_count: number;
  fallback_count: number;
  failed_sources: string[];
  needs_review_count: number;
}

export interface InnovationCandidate {
  claim: string;
  gap_type: string;
  supporting_papers: string[];
  contrast_papers: string[];
  analysis_basis: string[];
  supporting_evidence: string[];
  contrast_evidence: string[];
  novelty_reason: string;
  rare_reason: string;
  recommendation_reason: string;
  novelty_score: number;
  feasibility_score: number;
  risk_score: number;
  experiment_cost: number;
  undergrad_fit: number;
  evidence_strength: number;
  evidence_mode: "real" | "fallback";
  overall_score: number;
  risk: string;
  verification_plan: string;
}

export interface GapSummaryEntry {
  gap_type: string;
  focus: string;
  description: string;
  basis: string[];
  supporting_papers: string[];
  contrast_papers: string[];
  supporting_evidence: string[];
  contrast_evidence: string[];
  scarcity_score: number;
  coverage_score: number;
}

export interface EvidenceMapEntry {
  phrase: string;
  supporting_papers: string[];
  evidence: string[];
}

export interface GapAnalysisSummary {
  mode: "real" | "fallback";
  valid_record_count: number;
  record_count: number;
  common_methods: string[];
  common_datasets: string[];
  common_metrics: string[];
  common_limitations: string[];
  common_problems: string[];
  rare_methods: string[];
  rare_datasets: string[];
  rare_metrics: string[];
  method_diversity: number;
  dataset_diversity: number;
  metric_diversity: number;
  needs_review_count: number;
  method_gaps: GapSummaryEntry[];
  data_gaps: GapSummaryEntry[];
  scenario_gaps: GapSummaryEntry[];
  evaluation_gaps: GapSummaryEntry[];
  support_evidence_map: Record<string, EvidenceMapEntry[]>;
  contrast_evidence_map: Record<string, EvidenceMapEntry[]>;
  coverage_gaps: Record<string, string[]>;
}

export interface InnovationRecommendation {
  selected_claim: string;
  selected_gap_type: string;
  selected_reason: string;
  runner_up_claim: string;
  runner_up_score: number;
}

export interface ExperimentPlan {
  dataset: string[];
  baselines: string[];
  metrics: string[];
  ablations: string[];
  environment: string[];
  parameters: string[];
  dataset_notes: string[];
  baseline_notes: string[];
  metric_notes: string[];
  steps: string[];
  expected_outputs: string[];
  run_commands: Record<string, string>;
  result_files: string[];
  evidence_links: string[];
}

export interface ResultTable {
  name?: string;
  title?: string;
  columns: string[];
  rows?: Array<Record<string, string | number>>;
  source?: string;
  summary?: string;
}

export interface ResultFigure {
  name?: string;
  title?: string;
  caption?: string;
  source?: string;
  insight?: string;
}

export interface ConsistencyCheckItem {
  key: string;
  label: string;
  aligned: boolean;
  detail: string;
}

export interface ConsistencyFinding {
  key: string;
  label: string;
  aligned: boolean;
  detail: string;
  severity: "warning" | "error";
  blocking: boolean;
  source: string;
  target: string;
  message: string;
  recommendation: string;
  diffs?: Array<{
    field: string;
    expected: string;
    actual: string;
    status: string;
  }>;
  locations?: Array<{
    kind: string;
    path: string;
    label: string;
    snippet: string;
  }>;
}

export interface ArtifactBundle {
  literature_review?: string | null;
  innovation_report?: string | null;
  experiment_plan?: string | null;
  procedure?: string | null;
  thesis_docx?: string | null;
  thesis_pdf?: string | null;
  code_zip?: string | null;
  defense_pptx?: string | null;
  qa_report?: string | null;
}

export interface WorkflowNodeRun {
  node_name: string;
  phase: WorkflowPhase;
  status: WorkflowNodeStatus;
  attempt: number;
  started_at: string;
  ended_at: string;
  provider: string;
  model: string;
  fallback_used: boolean;
  message: string;
  error_category: FailureCategory;
  error_detail: string;
}

export interface AuditEvent {
  timestamp: string;
  level: "info" | "warning" | "error";
  phase: WorkflowPhase;
  node_name: string;
  message: string;
  attempt: number;
  provider: string;
  model: string;
  fallback_used: boolean;
}

export interface WorkflowCheckpoint {
  checkpoint_id: string;
  phase: WorkflowPhase;
  node_name: string;
  created_at: string;
  summary: string;
}

export interface RollbackRecord {
  from_phase: WorkflowPhase;
  to_phase: WorkflowPhase;
  reason: string;
  trigger_node: string;
  created_at: string;
  recovered: boolean;
}

export interface ProjectState {
  project_id: string;
  request: ProjectCreate;
  status: ProjectStatus;
  workflow_phase: WorkflowPhase;
  workflow_outcome: WorkflowOutcome;
  current_node: string;
  active_run_id: string;
  last_error: string;
  last_failure_category: FailureCategory;
  template_source?: TemplateSource | null;
  template_manifest?: TemplateManifest | null;
  uploaded_pdf_paths: string[];
  literature_records: LiteratureRecord[];
  retrieval_diagnostics: RetrievalDiagnostic[];
  retrieval_summary: RetrievalSummary;
  survey_table: Array<Record<string, unknown>>;
  literature_detail_fields: string[];
  innovation_candidates: InnovationCandidate[];
  selected_innovation?: InnovationCandidate | null;
  experiment_plan?: ExperimentPlan | null;
  result_schema: {
    gap_analysis?: GapAnalysisSummary;
    gap_analysis_overview?: string;
    innovation_recommendation?: InnovationRecommendation;
    procedure_document?: string;
    result_tables?: ResultTable[];
    result_figures?: ResultFigure[];
    result_analysis_text?: string;
    result_summary_for_paper?: string;
    result_summary_for_ppt?: string;
    result_key_findings?: string[];
    ppt_section_mapping?: Record<string, string>;
    consistency_summary?: {
      procedure_readme_aligned?: boolean;
      result_files_aligned?: boolean;
      plan_config_aligned?: boolean;
      paper_experiment_aligned?: boolean;
      ppt_mapping_aligned?: boolean;
      citation_binding_aligned?: boolean;
      paper_code_aligned?: boolean;
      checks?: ConsistencyCheckItem[];
      findings?: ConsistencyFinding[];
      blocking_count?: number;
      aligned_count?: number;
      total_checks?: number;
      warnings?: string[];
    };
    remediation_summary?: RemediationSummary;
    [key: string]: unknown;
  };
  generated_code_files: Record<string, string>;
  paper_outline: string[];
  paper_sections: Record<string, string>;
  ppt_outline: string[];
  review_findings: string[];
  warnings: string[];
  artifacts: ArtifactBundle;
  execution_log: string[];
  node_runs: Record<string, WorkflowNodeRun>;
  audit_trail: AuditEvent[];
  checkpoints: WorkflowCheckpoint[];
  rollback_history: RollbackRecord[];
}

export interface WorkflowStateSummary {
  project_id: string;
  status: ProjectStatus;
  workflow_phase: WorkflowPhase;
  workflow_outcome: WorkflowOutcome;
  current_node: string;
  last_error: string;
  last_failure_category: FailureCategory;
  node_runs: Record<string, WorkflowNodeRun>;
  checkpoints: WorkflowCheckpoint[];
  rollback_history: RollbackRecord[];
  audit_trail: AuditEvent[];
  blocking_findings: ConsistencyFinding[];
  consistency_summary?: ProjectState["result_schema"]["consistency_summary"];
}

export interface RemediationSummary {
  applied: boolean;
  applied_keys: string[];
  actions: Array<{
    key: string;
    status: string;
    message: string;
  }>;
  rerun_phases: string[];
}

export interface ProjectListItem {
  project_id: string;
  project_name: string;
  status: ProjectStatus;
  updated_at: string;
}

export interface ModelProviderSettings {
  id: string;
  label: string;
  api_base: string;
  api_key: string;
  priority: number;
  enabled: boolean;
  // API mode controls which OpenAI-compatible endpoint is used by this provider.
  // "chat_completions" -> /chat/completions, "responses" -> /responses.
  api_mode?: "chat_completions" | "responses";
  models: Partial<Record<ModelTaskType, string>>;
}

export interface ModelSettings {
  providers: ModelProviderSettings[];
  task_routes: Record<ModelTaskType, string>;
}

export interface ModelProviderTestPayload {
  provider: ModelProviderSettings;
}

export interface ModelProviderTestResult {
  ok: boolean;
  provider: string;
  model: string;
  message: string;
  response_preview?: string | null;
}
