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
}

export interface InnovationCandidate {
  claim: string;
  supporting_papers: string[];
  contrast_papers: string[];
  novelty_reason: string;
  feasibility_score: number;
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
  survey_table: Array<Record<string, unknown>>;
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
