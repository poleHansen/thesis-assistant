import { joinLines } from "../lib/format";
import type { ExperimentPlan } from "../lib/types";

interface ExperimentSummaryProps {
  plan?: ExperimentPlan | null;
}

export function ExperimentSummary({ plan }: ExperimentSummaryProps) {
  const commandEntries = plan ? Object.entries(plan.run_commands) : [];
  return (
    <section className="panel glass-card">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Experiment</p>
          <h3>实验计划摘要</h3>
        </div>
      </div>
      {!plan ? <p className="muted">项目运行完成后将在这里展示实验设计。</p> : null}
      {plan ? (
        <div className="summary-grid">
          <div>
            <span>数据集</span>
            <p>{joinLines(plan.dataset)}</p>
          </div>
          <div>
            <span>基线</span>
            <p>{joinLines(plan.baselines)}</p>
          </div>
          <div>
            <span>指标</span>
            <p>{joinLines(plan.metrics)}</p>
          </div>
          <div>
            <span>消融</span>
            <p>{joinLines(plan.ablations)}</p>
          </div>
          <div>
            <span>环境</span>
            <p>{joinLines(plan.environment)}</p>
          </div>
          <div>
            <span>参数</span>
            <p>{joinLines(plan.parameters)}</p>
          </div>
          <div className="summary-grid__full">
            <span>运行命令</span>
            <ul>
              {commandEntries.map(([name, command]) => (
                <li key={name}>
                  {name}：{command}
                </li>
              ))}
            </ul>
          </div>
          <div className="summary-grid__full">
            <span>结果文件</span>
            <ul>
              {plan.result_files.map((path) => (
                <li key={path}>{path}</li>
              ))}
            </ul>
          </div>
          <div className="summary-grid__full">
            <span>步骤</span>
            <ul>
              {plan.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}
