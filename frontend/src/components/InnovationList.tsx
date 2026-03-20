import type { GapAnalysisSummary, InnovationCandidate, InnovationRecommendation } from "../lib/types";

interface InnovationListProps {
  innovations: InnovationCandidate[];
  selectedClaim?: string | null;
  gapAnalysis?: GapAnalysisSummary;
  gapOverview?: string;
  recommendation?: InnovationRecommendation;
}

export function InnovationList({
  innovations,
  selectedClaim,
  gapAnalysis,
  gapOverview,
  recommendation,
}: InnovationListProps) {
  const evidenceModeText = (mode: InnovationCandidate["evidence_mode"]) =>
    mode === "real" ? "真实分析" : "占位推荐";

  const gapTypeText = (gapType: string) => {
    switch (gapType) {
      case "method_gap":
        return "方法空白";
      case "data_gap":
        return "数据空白";
      case "scenario_gap":
        return "场景空白";
      case "evaluation_gap":
        return "评价空白";
      default:
        return gapType;
    }
  };

  const renderInlineList = (items?: string[], fallback = "待补充") =>
    items && items.length > 0 ? items.join("、") : fallback;

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
    <section className="panel glass-card panel--scrollable panel--scrollable-innovation">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Innovation</p>
          <h3>候选创新点</h3>
        </div>
      </div>
      <div className="stack-list panel__content-scroll">
        {gapAnalysis ? (
          <article className="innovation-summary-card">
            <div className="innovation-summary-card__grid">
              <div>
                <small>分析模式</small>
                <strong>{evidenceModeText(gapAnalysis.mode)}</strong>
              </div>
              <div>
                <small>有效文献</small>
                <strong>{gapAnalysis.valid_record_count}</strong>
              </div>
              <div>
                <small>最明显 gap</small>
                <strong>{gapOverview || "待运行后生成"}</strong>
              </div>
              <div>
                <small>推荐说明</small>
                <strong>{recommendation?.selected_reason || "待排序后生成"}</strong>
              </div>
            </div>
            <div className="innovation-summary-card__grid innovation-summary-card__grid--compact">
              <div>
                <small>主流方法</small>
                <span>{renderInlineList(gapAnalysis.common_methods)}</span>
              </div>
              <div>
                <small>主流数据</small>
                <span>{renderInlineList(gapAnalysis.common_datasets)}</span>
              </div>
              <div>
                <small>主流评测</small>
                <span>{renderInlineList(gapAnalysis.common_metrics)}</span>
              </div>
              <div>
                <small>常见局限</small>
                <span>{renderInlineList(gapAnalysis.common_limitations)}</span>
              </div>
              <div>
                <small>罕见方法线索</small>
                <span>{renderInlineList(gapAnalysis.rare_methods)}</span>
              </div>
              <div>
                <small>罕见评测线索</small>
                <span>{renderInlineList(gapAnalysis.rare_metrics)}</span>
              </div>
            </div>
            <div className="stack-list">
              <p className="muted">
                当前候选会标注 real / fallback。real 表示基于结构化文献差异分析生成，fallback 表示证据不足时的占位推荐。
              </p>
              <p className="muted">
                若推荐项为 fallback，建议先补充文献；若为 real，可直接进入实验设计并继续补强对照实验。
              </p>
              <p className="muted">
                卡片中的“分析依据 / 支撑证据 / 对照依据”与下方证据映射都来自结构化文献字段摘要，用于快速核对推荐是否真正来自文献差异。
              </p>
            </div>
          </article>
        ) : null}
        {innovations.length === 0 ? <p className="muted">运行后会在这里展示候选创新点。</p> : null}
        {innovations.map((item, index) => (
          <article
            key={item.claim}
            className={`innovation-card ${selectedClaim === item.claim ? "innovation-card--active" : ""}`}
          >
            <div className="innovation-card__head">
              <div>
                <small>#{index + 1} · {gapTypeText(item.gap_type)}</small>
                <strong>{item.claim}</strong>
              </div>
              <span>{(item.overall_score || item.feasibility_score).toFixed(1)}</span>
            </div>
            <p>{item.novelty_reason}</p>
            <small>
              {gapTypeText(item.gap_type)} · 证据：{evidenceModeText(item.evidence_mode)} · 新颖性 {item.novelty_score.toFixed(1)} · 可行性 {item.feasibility_score.toFixed(1)}
            </small>
            <small>{item.recommendation_reason || "运行后会生成推荐理由。"}</small>
            <div className="innovation-score-row">
              <small>证据强度 {item.evidence_strength.toFixed(1)}</small>
              <small>风险 {item.risk_score.toFixed(1)}</small>
              <small>成本 {item.experiment_cost.toFixed(1)}</small>
              <small>本科适配 {item.undergrad_fit.toFixed(1)}</small>
            </div>
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
            <small>少见原因：{item.rare_reason || "待补充"}</small>
            <small>风险：{item.risk}</small>
            <small>验证计划：{item.verification_plan}</small>
          </article>
        ))}
        {gapAnalysis ? (
          <article className="innovation-summary-card">
            <div className="panel__header">
              <div>
                <p className="eyebrow">Gap Evidence Map</p>
                <h3>差异证据映射</h3>
              </div>
            </div>
            <div className="innovation-map-grid">
              {Object.entries(gapAnalysis.support_evidence_map ?? {}).map(([label, entries]) => {
                const first = entries?.[0];
                return (
                  <article key={`support-${label}`} className="paper-card">
                    <strong>支撑 · {label}</strong>
                    <span>{first?.phrase || "待补充"}</span>
                    <small>{renderInlineList(first?.supporting_papers, "暂无支撑文献")}</small>
                  </article>
                );
              })}
              {Object.entries(gapAnalysis.contrast_evidence_map ?? {}).map(([label, entries]) => {
                const first = entries?.[0];
                return (
                  <article key={`contrast-${label}`} className="paper-card">
                    <strong>对照 · {label}</strong>
                    <span>{first?.phrase || "待补充"}</span>
                    <small>{renderInlineList(first?.supporting_papers, "暂无对照文献")}</small>
                  </article>
                );
              })}
            </div>
          </article>
        ) : null}
      </div>
    </section>
  );
}
