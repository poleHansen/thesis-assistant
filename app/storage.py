from __future__ import annotations

from pathlib import Path

from app.config import SETTINGS


class ProjectStorage:
    def __init__(self, root: Path | None = None) -> None:
        SETTINGS.ensure_directories()
        self.root = root or SETTINGS.data_dir / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure_project_tree(self, project_id: str) -> Path:
        project_dir = self.root / project_id
        for child in (
            "inputs",
            "inputs/templates",
            "inputs/pdfs",
            "artifacts",
            "artifacts/code",
            "artifacts/reports",
            "artifacts/slides",
        ):
            (project_dir / child).mkdir(parents=True, exist_ok=True)
        return project_dir

    def save_binary(self, project_id: str, relative_path: str, content: bytes) -> Path:
        project_dir = self.ensure_project_tree(project_id)
        path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def resolve(self, project_id: str, relative_path: str) -> Path:
        return self.ensure_project_tree(project_id) / relative_path

