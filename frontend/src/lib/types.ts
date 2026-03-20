export type ProjectStatus = "created" | "running" | "completed" | "failed";
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

export interface ExperimentPlan {
  dataset: string[];
  baselines: string[];
  metrics: string[];
  ablations: string[];
  environment: string[];
  steps: string[];
  expected_outputs: string[];
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

export interface ProjectState {
  project_id: string;
  request: ProjectCreate;
  status: ProjectStatus;
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
  result_schema: Record<string, unknown>;
  generated_code_files: Record<string, string>;
  paper_outline: string[];
  paper_sections: Record<string, string>;
  ppt_outline: string[];
  review_findings: string[];
  warnings: string[];
  artifacts: ArtifactBundle;
  execution_log: string[];
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
