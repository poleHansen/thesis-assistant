import type {
  ArtifactBundle,
  ModelProviderTestPayload,
  ModelProviderTestResult,
  ModelSettings,
  ProjectCreate,
  ProjectListItem,
  ProjectState,
  RemediationSummary,
  UploadKind,
  WorkflowStateSummary,
} from "./types";

const API_BASE = "/api";

async function requestJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listProjects() {
  return requestJson<ProjectListItem[]>(`${API_BASE}/projects`);
}

export function getModelSettings() {
  return requestJson<ModelSettings>(`${API_BASE}/settings/models`);
}

export function updateModelSettings(payload: ModelSettings) {
  return requestJson<ModelSettings>(`${API_BASE}/settings/models`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function testModelProvider(payload: ModelProviderTestPayload) {
  return requestJson<ModelProviderTestResult>(`${API_BASE}/settings/models/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function createProject(payload: ProjectCreate) {
  return requestJson<{ project_id: string; state: ProjectState }>(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getProject(projectId: string) {
  return requestJson<ProjectState>(`${API_BASE}/projects/${projectId}`);
}

export function getProjectWorkflow(projectId: string) {
  return requestJson<WorkflowStateSummary>(`${API_BASE}/projects/${projectId}/workflow`);
}

export async function uploadProjectFile(projectId: string, kind: UploadKind, file: File) {
  const formData = new FormData();
  formData.append("kind", kind);
  formData.append("file", file);
  return requestJson<{ project_id: string; saved: string; kind: UploadKind }>(
    `${API_BASE}/projects/${projectId}/files`,
    { method: "POST", body: formData },
  );
}

export function runProject(projectId: string) {
  return requestJson<{ project_id: string; status: string; artifacts: ArtifactBundle }>(
    `${API_BASE}/projects/${projectId}/run`,
    { method: "POST" },
  );
}

export function repairProject(projectId: string) {
  return requestJson<{ project_id: string; status: string; workflow_outcome: string; remediation_summary: RemediationSummary }>(
    `${API_BASE}/projects/${projectId}/repair`,
    { method: "POST" },
  );
}

export function listArtifacts(projectId: string) {
  return requestJson<ArtifactBundle>(`${API_BASE}/projects/${projectId}/artifacts`);
}

export function getArtifactDownloadUrl(projectId: string, artifactName: keyof ArtifactBundle) {
  return `${API_BASE}/projects/${projectId}/artifacts/${artifactName}`;
}

const artifactFilenameFallback: Record<keyof ArtifactBundle, string> = {
  literature_review: "literature_review.xlsx",
  innovation_report: "innovation_report.md",
  experiment_plan: "experiment_plan.docx",
  procedure: "procedure.docx",
  thesis_docx: "thesis.docx",
  thesis_pdf: "thesis.pdf",
  code_zip: "code_bundle.zip",
  defense_pptx: "defense.pptx",
  qa_report: "qa_report.json",
};

function getFilenameFromDisposition(contentDisposition: string | null) {
  if (!contentDisposition) {
    return null;
  }
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }
  const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return asciiMatch?.[1] ?? null;
}

export async function downloadArtifact(projectId: string, artifactName: keyof ArtifactBundle) {
  const response = await fetch(getArtifactDownloadUrl(projectId, artifactName));
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const filename =
    getFilenameFromDisposition(response.headers.get("Content-Disposition")) ||
    artifactFilenameFallback[artifactName];

  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(objectUrl);
}
