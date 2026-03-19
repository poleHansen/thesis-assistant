from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import SETTINGS
from app.domain import ProjectCreate, ProjectState
from app.model_gateway import ModelGateway
from app.model_settings import ModelSettingsError, ModelSettingsStore
from app.repository import ProjectRepository
from app.storage import ProjectStorage
from app.template_service import TemplateService
from app.utils import to_plain_data
from app.workflow import LangGraphSupervisor


SETTINGS.ensure_directories()
repository = ProjectRepository()
storage = ProjectStorage()
model_settings_store = ModelSettingsStore()
gateway = ModelGateway(model_settings_store.load())
template_service = TemplateService()
supervisor = LangGraphSupervisor(repository, storage, gateway, template_service)

app = FastAPI(title="Thesis Assistant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/projects")
def list_projects() -> list[dict[str, str]]:
    return repository.list_projects()


@app.get("/settings/models")
def get_model_settings() -> dict:
    return to_plain_data(gateway.get_settings())


@app.put("/settings/models")
def update_model_settings(payload: dict) -> dict:
    try:
        settings = model_settings_store.save(payload)
    except ModelSettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    gateway.reload(settings)
    return to_plain_data(settings)


@app.post("/projects")
def create_project(payload: dict) -> dict:
    try:
        request_model = ProjectCreate(**payload)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    project_id = f"{uuid4().hex[:8]}-{uuid4().hex[:8]}"
    storage.ensure_project_tree(project_id)
    state = ProjectState(project_id=project_id, request=request_model)
    repository.create(state)
    return {"project_id": project_id, "state": to_plain_data(state)}


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    state = repository.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Project not found")
    return to_plain_data(state)


@app.post("/projects/{project_id}/files")
async def upload_file(
    project_id: str,
    kind: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    state = repository.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    filename = file.filename or "upload.bin"
    if kind == "word_template":
        relative = f"inputs/templates/{filename}"
        saved_path = storage.save_binary(project_id, relative, content)
        source, manifest = template_service.parse_user_template(saved_path)
        state.template_source = source
        state.template_manifest = manifest
    elif kind == "ppt_template":
        relative = f"inputs/templates/{filename}"
        saved_path = storage.save_binary(project_id, relative, content)
        state.result_schema["ppt_template_path"] = str(saved_path)
    elif kind == "paper_pdf":
        relative = f"inputs/pdfs/{filename}"
        saved_path = storage.save_binary(project_id, relative, content)
        state.uploaded_pdf_paths.append(str(saved_path))
    else:
        raise HTTPException(
            status_code=400,
            detail="kind must be word_template, ppt_template, or paper_pdf",
        )

    repository.save(state)
    return {"project_id": project_id, "saved": filename, "kind": kind}


@app.post("/projects/{project_id}/run")
def run_project(project_id: str) -> dict:
    state = repository.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        updated = supervisor.run(state)
    except Exception as exc:
        state.status = "failed"
        state.warnings.append(str(exc))
        repository.save(state)
        raise HTTPException(status_code=500, detail=f"Workflow failed: {exc}") from exc
    return {
        "project_id": project_id,
        "status": updated.status,
        "artifacts": to_plain_data(updated.artifacts),
    }


@app.get("/projects/{project_id}/artifacts")
def list_artifacts(project_id: str) -> dict:
    state = repository.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Project not found")
    return to_plain_data(state.artifacts)


@app.get("/projects/{project_id}/artifacts/{artifact_name}")
def download_artifact(project_id: str, artifact_name: str) -> FileResponse:
    state = repository.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Project not found")
    artifact_map = to_plain_data(state.artifacts)
    path = artifact_map.get(artifact_name)
    if not path:
        raise HTTPException(status_code=404, detail="Artifact not found")
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")
    return FileResponse(file_path)
