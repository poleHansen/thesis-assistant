import type {
  ArtifactBundle,
  ModelProviderTestPayload,
  ModelProviderTestResult,
  ModelSettings,
  ProjectCreate,
  ProjectListItem,
  ProjectState,
  UploadKind,
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

export function listArtifacts(projectId: string) {
  return requestJson<ArtifactBundle>(`${API_BASE}/projects/${projectId}/artifacts`);
}

export function getArtifactDownloadUrl(projectId: string, artifactName: keyof ArtifactBundle) {
  return `${API_BASE}/projects/${projectId}/artifacts/${artifactName}`;
}
