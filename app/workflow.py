from __future__ import annotations

import os
from typing import Callable

from app.agents import AGENT_PIPELINE
from app.artifact_service import ArtifactService
from app.domain import ProjectState
from app.model_gateway import ModelGateway
from app.repository import ProjectRepository
from app.storage import ProjectStorage
from app.template_service import TemplateService


class LangGraphSupervisor:
    def __init__(
        self,
        repository: ProjectRepository,
        storage: ProjectStorage,
        gateway: ModelGateway,
        template_service: TemplateService,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.gateway = gateway
        self.template_service = template_service
        self.artifact_service = ArtifactService(storage)
        self._graph_runner = self._build_runner()

    def _build_runner(self) -> Callable[[ProjectState], ProjectState]:
        if os.getenv("THESIS_ASSISTANT_ENABLE_LANGGRAPH", "0") != "1":
            return self._run_sequential
        try:
            from langgraph.graph import END, StateGraph  # type: ignore
        except Exception:
            return self._run_sequential

        graph = StateGraph(ProjectState)
        for agent_cls in AGENT_PIPELINE:
            graph.add_node(agent_cls.name, self._make_node(agent_cls))

        graph.set_entry_point(AGENT_PIPELINE[0].name)
        for current, nxt in zip(AGENT_PIPELINE, AGENT_PIPELINE[1:]):
            graph.add_edge(current.name, nxt.name)
        graph.add_edge(AGENT_PIPELINE[-1].name, END)
        compiled = graph.compile()
        return compiled.invoke

    def _make_node(self, agent_cls: type) -> Callable[[ProjectState], ProjectState]:
        def node(state: ProjectState) -> ProjectState:
            agent = agent_cls(self.gateway)
            return agent.run(state)

        return node

    def _run_sequential(self, state: ProjectState) -> ProjectState:
        for agent_cls in AGENT_PIPELINE:
            agent = agent_cls(self.gateway)
            state = agent.run(state)
        return state

    def run(self, state: ProjectState) -> ProjectState:
        state.status = "running"
        self.repository.save(state)

        if state.template_source is None or state.template_manifest is None:
            source, manifest = self.template_service.choose_default_template(state.request)
            state.template_source = source
            state.template_manifest = manifest
            state.execution_log.append("template_selector: used default template library")

        state = self._graph_runner(state)
        state = self.artifact_service.render_all(state)
        state.status = "completed"
        self.repository.save(state)
        return state
