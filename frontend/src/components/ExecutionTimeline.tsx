interface ExecutionTimelineProps {
  logs: string[];
  warnings: string[];
}

export function ExecutionTimeline({ logs, warnings }: ExecutionTimelineProps) {
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
        {logs.map((log, index) => (
          <div key={`${log}-${index}`} className="timeline-list__item">
            <span className="timeline-list__dot" />
            <span>{log}</span>
          </div>
        ))}
      </div>
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
