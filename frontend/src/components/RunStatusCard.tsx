import type { ProjectState } from "../lib/types";
import { statusText } from "../lib/format";

interface RunStatusCardProps {
  project?: ProjectState;
  running?: boolean;
  onRun: () => Promise<void>;
}

export function RunStatusCard({ project, running, onRun }: RunStatusCardProps) {
  const status = project?.status ?? "created";

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
