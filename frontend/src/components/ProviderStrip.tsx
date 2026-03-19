const providers = [
  ["OpenAI", "适合规划、审稿、一致性检查等高要求任务。"],
  ["DeepSeek", "适合代码规划、代码生成和成本更敏感的链路。"],
  ["Kimi / Moonshot", "适合中文长上下文综述、章节润色和材料整合。"],
];

export function ProviderStrip() {
  return (
    <section className="section">
      <div className="section__heading">
        <p className="eyebrow">Model Providers</p>
        <h2>兼容常见中外大模型提供商，按任务做路由与回退。</h2>
      </div>
      <div className="provider-strip">
        {providers.map(([name, desc]) => (
          <div key={name} className="provider-pill">
            <strong>{name}</strong>
            <span>{desc}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
