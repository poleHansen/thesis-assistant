import type { InnovationCandidate } from "../lib/types";

interface InnovationListProps {
  innovations: InnovationCandidate[];
  selectedClaim?: string | null;
}

export function InnovationList({ innovations, selectedClaim }: InnovationListProps) {
  const evidenceModeText = (mode: InnovationCandidate["evidence_mode"]) =>
    mode === "real" ? "真实分析" : "占位推荐";

  const renderEvidenceList = (title: string, items: string[], maxItems: number) => {
    if (items.length === 0) return null;
    return (
      <div>
        <small>{title}</small>
        {items.slice(0, maxItems).map((entry) => (
          <small key={`${title}-${entry}`}>{entry}</small>
        ))}
      </div>
    );
  };

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
              <span>{(item.overall_score || item.feasibility_score).toFixed(1)}</span>
            </div>
            <p>{item.novelty_reason}</p>
            <small>
              {item.gap_type} · 证据：{evidenceModeText(item.evidence_mode)} · 新颖性 {item.novelty_score.toFixed(1)} · 可行性 {item.feasibility_score.toFixed(1)}
            </small>
            <small>{item.recommendation_reason || "运行后会生成推荐理由。"}</small>
            {item.evidence_mode === "real"
              ? (
                <>
                  {renderEvidenceList("分析依据", item.analysis_basis, 3)}
                  {renderEvidenceList("支撑证据", item.supporting_evidence, 2)}
                  {renderEvidenceList("对照依据", item.contrast_evidence, 2)}
                </>
              )
              : null}
            {item.evidence_mode === "fallback" ? <small>提示：当前候选需要人工补充文献后再确认。</small> : null}
            <small>风险：{item.risk}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
