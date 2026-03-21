from __future__ import annotations

import os
from typing import Callable

from app.agents import (
    AGENT_PIPELINE,
    CitationBinderAgent,
    ConsistencyCheckerAgent,
    DeckPlannerAgent,
    EvidenceExtractorAgent,
    ExperimentDesignerAgent,
    FeasibilityReviewerAgent,
    GapAnalystAgent,
    NoveltyJudgeAgent,
    OutlineWriterAgent,
    ProcedureWriterAgent,
    ReaderAgent,
    ResultAnalystAgent,
    ResultSchemaAgent,
    RetrieverAgent,
    ReviewerAgent,
    SectionWriterAgent,
    SurveySynthesizerAgent,
    TopicPlannerAgent,
    CodeAgent,
    CodePlannerAgent,
)
from app.artifact_service import ArtifactService
from app.domain import AuditEvent, ProjectState, RollbackRecord, WorkflowCheckpoint, WorkflowNodeRun
from app.model_gateway import ModelGateway
from app.repository import ProjectRepository
from app.storage import ProjectStorage
from app.template_service import TemplateService
from app.utils import utcnow_iso


PHASE_PIPELINE: list[tuple[str, list[type]]] = [
    ("planning", [TopicPlannerAgent]),
    (
        "research",
        [
            RetrieverAgent,
            ReaderAgent,
            EvidenceExtractorAgent,
            SurveySynthesizerAgent,
            GapAnalystAgent,
            NoveltyJudgeAgent,
            FeasibilityReviewerAgent,
        ],
    ),
    (
        "implementation",
        [
            ExperimentDesignerAgent,
            ProcedureWriterAgent,
            ResultSchemaAgent,
            ResultAnalystAgent,
            CodePlannerAgent,
            CodeAgent,
        ],
    ),
    ("writing_delivery", [OutlineWriterAgent, SectionWriterAgent, CitationBinderAgent, DeckPlannerAgent]),
    ("review", [ConsistencyCheckerAgent, ReviewerAgent]),
]


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
            return self._run_layered
        try:
            from langgraph.graph import END, StateGraph  # type: ignore
        except Exception:
            return self._run_layered

        graph = StateGraph(ProjectState)
        for phase_name, _ in PHASE_PIPELINE:
            graph.add_node(phase_name, self._make_phase_node(phase_name))

        graph.set_entry_point(PHASE_PIPELINE[0][0])
        for (current, _), (nxt, _) in zip(PHASE_PIPELINE, PHASE_PIPELINE[1:]):
            graph.add_edge(current, nxt)
        graph.add_edge(PHASE_PIPELINE[-1][0], END)
        compiled = graph.compile()
        return compiled.invoke

    def _make_phase_node(self, phase_name: str) -> Callable[[ProjectState], ProjectState]:
        def node(state: ProjectState) -> ProjectState:
            return self._run_phase(state, phase_name)

        return node

    def _run_layered(self, state: ProjectState) -> ProjectState:
        for phase_name, _ in PHASE_PIPELINE:
            state = self._run_phase(state, phase_name)
        unresolved_before = self._review_has_blockers(state)
        if unresolved_before:
            state = self._rollback_and_retry(state, "review", "writing_delivery", "Review layer detected unresolved consistency issues")
        state.workflow_phase = "completed"
        state.current_node = ""
        if state.rollback_history and any(item.recovered for item in state.rollback_history):
            state.workflow_outcome = "rollback_success"
        elif self._review_has_blockers(state):
            state.workflow_outcome = "partial_success"
        else:
            state.workflow_outcome = "success"
        return state

    def _run_phase(self, state: ProjectState, phase_name: str) -> ProjectState:
        agents = next((items for name, items in PHASE_PIPELINE if name == phase_name), [])
        state.workflow_phase = phase_name
        self._append_audit_event(state, phase_name, "", f"phase {phase_name} started")
        for agent_cls in agents:
            state = self._execute_agent(state, phase_name, agent_cls)
        checkpoint_node = agents[-1].name if agents else ""
        self._record_checkpoint(state, phase_name, checkpoint_node, f"phase {phase_name} completed")
        self._append_audit_event(state, phase_name, checkpoint_node, f"phase {phase_name} completed")
        self.repository.save(state)
        return state

    def _execute_agent(self, state: ProjectState, phase_name: str, agent_cls: type) -> ProjectState:
        node_name = agent_cls.name
        previous = state.node_runs.get(node_name)
        attempt = (previous.attempt if previous else 0) + 1
        run = WorkflowNodeRun(
            node_name=node_name,
            phase=phase_name,
            status="running",
            attempt=attempt,
            started_at=utcnow_iso(),
            ended_at="",
            provider=previous.provider if previous else "",
            model=previous.model if previous else "",
            fallback_used=previous.fallback_used if previous else False,
            message="running",
        )
        state.current_node = node_name
        state.workflow_phase = phase_name
        state.node_runs[node_name] = run
        self._append_audit_event(state, phase_name, node_name, f"{node_name} started", attempt=attempt)
        self.repository.save(state)
        try:
            agent = agent_cls(self.gateway)
            state = agent.run(state)
            node_run = state.node_runs.get(node_name, run)
            node_run.phase = phase_name
            node_run.status = "succeeded"
            node_run.attempt = attempt
            node_run.ended_at = utcnow_iso()
            node_run.message = "completed"
            state.node_runs[node_name] = node_run
            self._append_audit_event(state, phase_name, node_name, f"{node_name} completed", attempt=attempt)
            self.repository.save(state)
            return state
        except Exception as exc:
            run.status = "failed"
            run.attempt = attempt
            run.ended_at = utcnow_iso()
            run.error_category = self._categorize_failure(node_name, exc)
            run.error_detail = str(exc)
            run.message = "failed"
            state.node_runs[node_name] = run
            state.last_error = str(exc)
            state.last_failure_category = run.error_category
            self._append_audit_event(
                state,
                phase_name,
                node_name,
                f"{node_name} failed: {exc}",
                level="error",
                attempt=attempt,
            )
            self.repository.save(state)
            raise

    def _rollback_and_retry(
        self,
        state: ProjectState,
        from_phase: str,
        to_phase: str,
        reason: str,
    ) -> ProjectState:
        if any(record.reason == reason for record in state.rollback_history):
            return state
        trigger_node = state.current_node or from_phase
        rollback = RollbackRecord(
            from_phase=from_phase,
            to_phase=to_phase,
            reason=reason,
            trigger_node=trigger_node,
            created_at=utcnow_iso(),
            recovered=False,
        )
        state.rollback_history.append(rollback)
        self._append_audit_event(state, from_phase, trigger_node, reason, level="warning")
        for phase_name, agents in PHASE_PIPELINE:
            if phase_name not in {to_phase, "review"}:
                continue
            for agent_cls in agents:
                node_name = agent_cls.name
                if node_name in state.node_runs and state.node_runs[node_name].status == "succeeded":
                    state.node_runs[node_name].status = "rolled_back"
            state = self._run_phase(state, phase_name)
        rollback.recovered = not self._review_has_blockers(state)
        return state

    def _record_checkpoint(self, state: ProjectState, phase_name: str, node_name: str, summary: str) -> None:
        checkpoint = WorkflowCheckpoint(
            checkpoint_id=f"{phase_name}-{len(state.checkpoints) + 1}",
            phase=phase_name,
            node_name=node_name,
            created_at=utcnow_iso(),
            summary=summary,
        )
        state.checkpoints.append(checkpoint)

    def _append_audit_event(
        self,
        state: ProjectState,
        phase_name: str,
        node_name: str,
        message: str,
        *,
        level: str = "info",
        attempt: int = 0,
    ) -> None:
        state.audit_trail.append(
            AuditEvent(
                timestamp=utcnow_iso(),
                level=level,
                phase=phase_name,
                node_name=node_name,
                message=message,
                attempt=attempt,
            )
        )

    def _review_has_blockers(self, state: ProjectState) -> bool:
        consistency_summary = state.result_schema.get("consistency_summary", {})
        if not isinstance(consistency_summary, dict):
            return False
        findings = consistency_summary.get("findings", [])
        if isinstance(findings, list):
            return any(bool(item.get("blocking")) for item in findings if isinstance(item, dict))
        checks = consistency_summary.get("checks", [])
        return any(not bool(check.get("aligned")) for check in checks if isinstance(check, dict))

    def _categorize_failure(self, node_name: str, exc: Exception) -> str:
        lowered = str(exc).lower()
        if "timeout" in lowered or "rate limit" in lowered or "temporarily" in lowered:
            return "transient"
        if "consistency" in node_name or "review" in node_name:
            return "consistency"
        if "artifact" in lowered or "render" in lowered or "template" in lowered:
            return "rendering"
        if isinstance(exc, ValueError):
            return "validation"
        return "unknown"

    def run(self, state: ProjectState) -> ProjectState:
        state.status = "running"
        state.workflow_phase = "planning"
        state.workflow_outcome = "not_started"
        state.active_run_id = utcnow_iso()
        state.last_error = ""
        state.last_failure_category = "unknown"
        self.repository.save(state)

        if state.template_source is None or state.template_manifest is None:
            source, manifest = self.template_service.choose_default_template(state.request)
            state.template_source = source
            state.template_manifest = manifest
            state.execution_log.append("template_selector: used default template library")
            self._append_audit_event(state, "intake", "template_selector", "used default template library")

        try:
            state = self._graph_runner(state)
            self._append_audit_event(state, "completed", "artifact_service", "artifact rendering started")
            state = self.artifact_service.render_all(state)
            self._append_audit_event(state, "completed", "artifact_service", "artifact rendering completed")
            state.status = "completed"
            self.repository.save(state)
            return state
        except Exception as exc:
            state.status = "failed"
            state.workflow_outcome = "failed"
            state.last_error = str(exc)
            state.execution_log.append(f"workflow: failed with {exc}")
            self._append_audit_event(state, state.workflow_phase, state.current_node, f"workflow failed: {exc}", level="error")
            self.repository.save(state)
            raise
