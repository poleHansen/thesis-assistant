import type { AuditEvent, ConsistencyFinding, RollbackRecord, WorkflowCheckpoint, WorkflowNodeRun } from "../lib/types";

interface ExecutionTimelineProps {
  logs: string[];
  warnings: string[];
  auditTrail?: AuditEvent[];
  rollbackHistory?: RollbackRecord[];
  nodeRuns?: Record<string, WorkflowNodeRun>;
  checkpoints?: WorkflowCheckpoint[];
  blockingFindings?: ConsistencyFinding[];
}

export function ExecutionTimeline({ logs, warnings, auditTrail = [], rollbackHistory = [], nodeRuns = {}, checkpoints = [], blockingFindings = [] }: ExecutionTimelineProps) {
  const runItems = Object.values(nodeRuns)
    .sort((left, right) => (left.started_at < right.started_at ? -1 : 1))
    .slice(-8);

  return (
    <section className="panel glass-card">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Execution Log</p>
          <h3>执行时间线</h3>
        </div>
      </div>
      <div className="timeline-list">
        {logs.length === 0 ? <p className="muted">暂无执行日志。</p> : null}
        {runItems.length > 0
          ? runItems.map((run) => (
              <div key={`${run.node_name}-${run.attempt}-${run.started_at}`} className="timeline-list__item">
                <span className="timeline-list__dot" />
                <span>
                  [{run.phase}] {run.node_name}: {run.status}
                  {run.error_detail ? ` / ${run.error_detail}` : ""}
                </span>
              </div>
            ))
          : null}
        {auditTrail.length > 0
          ? auditTrail.slice(-8).map((event, index) => (
              <div key={`${event.timestamp}-${event.node_name}-${index}`} className="timeline-list__item">
                <span className="timeline-list__dot" />
                <span>
                  [{event.phase}] {event.node_name || "system"}: {event.message}
                </span>
              </div>
            ))
          : null}
        {logs.map((log, index) => (
          <div key={`${log}-${index}`} className="timeline-list__item">
            <span className="timeline-list__dot" />
            <span>{log}</span>
          </div>
        ))}
      </div>
      {checkpoints.length > 0 ? (
        <div className="warning-box">
          <strong>检查点</strong>
          <ul>
            {checkpoints.slice(-4).map((item) => (
              <li key={item.checkpoint_id}>
                {item.phase} / {item.node_name || "system"}：{item.summary}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {blockingFindings.length > 0 ? (
        <div className="warning-box">
          <strong>阻塞项</strong>
          <ul>
            {blockingFindings.map((item) => (
              <li key={`${item.key}-${item.source}-${item.target}`}>
                {item.label}：{item.recommendation}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {rollbackHistory.length > 0 ? (
        <div className="warning-box">
          <strong>回退记录</strong>
          <ul>
            {rollbackHistory.map((item, index) => (
              <li key={`${item.created_at}-${index}`}>
                {item.from_phase} → {item.to_phase}：{item.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <div className="warning-box">
          <strong>提醒</strong>
          <ul>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
