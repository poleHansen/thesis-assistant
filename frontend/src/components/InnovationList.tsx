import type { InnovationCandidate } from "../lib/types";

interface InnovationListProps {
  innovations: InnovationCandidate[];
  selectedClaim?: string | null;
}

export function InnovationList({ innovations, selectedClaim }: InnovationListProps) {
  return (
    <section className="panel glass-card">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Innovation</p>
          <h3>候选创新点</h3>
        </div>
      </div>
      <div className="stack-list">
        {innovations.length === 0 ? <p className="muted">运行后会在这里展示候选创新点。</p> : null}
        {innovations.map((item) => (
          <article
            key={item.claim}
            className={`innovation-card ${selectedClaim === item.claim ? "innovation-card--active" : ""}`}
          >
            <div className="innovation-card__head">
              <strong>{item.claim}</strong>
              <span>{item.feasibility_score.toFixed(1)}</span>
            </div>
            <p>{item.novelty_reason}</p>
            <small>风险：{item.risk}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
