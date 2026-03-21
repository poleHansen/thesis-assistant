import type { ProjectState } from "../lib/types";
import { statusText } from "../lib/format";

interface RunStatusCardProps {
  project?: ProjectState;
  running?: boolean;
  onRun: () => Promise<void>;
}

export function RunStatusCard({ project, running, onRun }: RunStatusCardProps) {
  const status = project?.status ?? "created";
  const workflowPhase = project?.workflow_phase ?? "intake";
  const workflowOutcome = project?.workflow_outcome ?? "not_started";
  const currentNode = project?.current_node ?? "";
  const lastError = project?.last_error ?? "";
  const lastFailureCategory = project?.last_failure_category ?? "unknown";

  return (
    <section className="panel glass-card">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Workflow</p>
          <h3>运行多智能体工作流</h3>
        </div>
        <span className={`status-pill status-pill--${status}`}>{statusText[status]}</span>
      </div>
      <p className="panel__text">
        运行后将依次执行文献检索、创新点分析、实验设计、代码骨架生成、论文模板化输出和答辩材料生成。
      </p>
      <div className="stack-list">
        <p className="muted">当前阶段：{workflowPhase}</p>
        <p className="muted">执行结果：{workflowOutcome}</p>
        {currentNode ? <p className="muted">当前节点：{currentNode}</p> : null}
        {lastError ? <p className="muted">最近错误：{lastFailureCategory} / {lastError}</p> : null}
      </div>
      <button
        className="button button--primary"
        disabled={!project || running || status === "running"}
        onClick={() => {
          void onRun();
        }}
      >
        {running || status === "running" ? "运行中..." : "启动生成"}
      </button>
    </section>
  );
}
