from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import fields
from pathlib import Path

from app.config import SETTINGS
from app.domain import (
    AuditEvent,
    ArtifactBundle,
    ExperimentPlan,
    RollbackRecord,
    InnovationCandidate,
    LiteratureRecord,
    ProjectCreate,
    ProjectState,
    RetrievalSummary,
    TemplateManifest,
    TemplateSource,
    WorkflowCheckpoint,
    WorkflowNodeRun,
)
from app.utils import dumps_json, loads_json, utcnow_iso


class ProjectRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        SETTINGS.ensure_directories()
        self.db_path = db_path or SETTINGS.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    template_source_json TEXT,
                    template_manifest_json TEXT,
                    uploaded_pdf_paths_json TEXT,
                    state_json TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create(self, state: ProjectState) -> None:
        now = utcnow_iso()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    id, status, request_json, template_source_json, template_manifest_json,
                    uploaded_pdf_paths_json, state_json, artifacts_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.project_id,
                    state.status,
                    dumps_json(state.request),
                    dumps_json(state.template_source) if state.template_source else None,
                    dumps_json(state.template_manifest) if state.template_manifest else None,
                    dumps_json(state.uploaded_pdf_paths),
                    dumps_json(state),
                    dumps_json(state.artifacts),
                    now,
                    now,
                ),
            )
            conn.commit()

    def save(self, state: ProjectState) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE projects
                SET status = ?,
                    request_json = ?,
                    template_source_json = ?,
                    template_manifest_json = ?,
                    uploaded_pdf_paths_json = ?,
                    state_json = ?,
                    artifacts_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    state.status,
                    dumps_json(state.request),
                    dumps_json(state.template_source) if state.template_source else None,
                    dumps_json(state.template_manifest) if state.template_manifest else None,
                    dumps_json(state.uploaded_pdf_paths),
                    dumps_json(state),
                    dumps_json(state.artifacts),
                    utcnow_iso(),
                    state.project_id,
                ),
            )
            conn.commit()

    def get(self, project_id: str) -> ProjectState | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT request_json, state_json
                FROM projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()

        if not row:
            return None

        request_data = loads_json(row[0], {})
        state_data = loads_json(row[1], {})
        return self._build_state(state_data, request_data)

    def list_projects(self) -> list[dict[str, str]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, status, updated_at, request_json
                FROM projects
                ORDER BY updated_at DESC
                """
            ).fetchall()
        items: list[dict[str, str]] = []
        for project_id, status, updated_at, request_json in rows:
            request_data = loads_json(request_json, {})
            topic = str(request_data.get("topic", "")).strip() or "未命名项目"
            items.append(
                {
                    "project_id": project_id,
                    "project_name": topic,
                    "status": status,
                    "updated_at": updated_at,
                }
            )
        return items

    def _build_state(self, state_data: dict, request_data: dict) -> ProjectState:
        request = ProjectCreate(**request_data)

        template_source = (
            TemplateSource(**state_data["template_source"])
            if state_data.get("template_source")
            else None
        )
        template_manifest = (
            TemplateManifest(**state_data["template_manifest"])
            if state_data.get("template_manifest")
            else None
        )

        allowed = {field.name for field in fields(ProjectState)}
        kwargs = {key: value for key, value in state_data.items() if key in allowed}
        kwargs["request"] = request
        kwargs["template_source"] = template_source
        kwargs["template_manifest"] = template_manifest
        kwargs["literature_records"] = [
            LiteratureRecord(**self._filter_dataclass_kwargs(LiteratureRecord, item))
            for item in state_data.get("literature_records", [])
        ]
        kwargs["innovation_candidates"] = [
            InnovationCandidate(**self._filter_dataclass_kwargs(InnovationCandidate, item))
            for item in state_data.get("innovation_candidates", [])
        ]
        kwargs["selected_innovation"] = (
            InnovationCandidate(
                **self._filter_dataclass_kwargs(InnovationCandidate, state_data["selected_innovation"])
            )
            if state_data.get("selected_innovation")
            else None
        )
        kwargs["experiment_plan"] = (
            ExperimentPlan(**self._filter_dataclass_kwargs(ExperimentPlan, state_data["experiment_plan"]))
            if state_data.get("experiment_plan")
            else None
        )
        kwargs["retrieval_summary"] = RetrievalSummary(
            **self._filter_dataclass_kwargs(RetrievalSummary, state_data.get("retrieval_summary", {}))
        )
        kwargs["artifacts"] = ArtifactBundle(
            **self._filter_dataclass_kwargs(ArtifactBundle, state_data.get("artifacts", {}))
        )
        kwargs["node_runs"] = {
            str(key): WorkflowNodeRun(**self._filter_dataclass_kwargs(WorkflowNodeRun, value))
            for key, value in dict(state_data.get("node_runs", {})).items()
            if isinstance(value, dict)
        }
        kwargs["audit_trail"] = [
            AuditEvent(**self._filter_dataclass_kwargs(AuditEvent, item))
            for item in state_data.get("audit_trail", [])
            if isinstance(item, dict)
        ]
        kwargs["checkpoints"] = [
            WorkflowCheckpoint(**self._filter_dataclass_kwargs(WorkflowCheckpoint, item))
            for item in state_data.get("checkpoints", [])
            if isinstance(item, dict)
        ]
        kwargs["rollback_history"] = [
            RollbackRecord(**self._filter_dataclass_kwargs(RollbackRecord, item))
            for item in state_data.get("rollback_history", [])
            if isinstance(item, dict)
        ]
        return ProjectState(**kwargs)

    def _filter_dataclass_kwargs(self, model_cls: type, payload: dict | None) -> dict:
        payload = payload or {}
        allowed = {field.name for field in fields(model_cls)}
        return {key: value for key, value in payload.items() if key in allowed}
