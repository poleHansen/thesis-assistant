const features = [
  ["文献检索", "自动聚合开放文献源，并允许上传 PDF 作为证据补充。"],
  ["创新点候选", "从综述与差异对比中提炼低重合、可验证的研究切入点。"],
  ["模板输出", "有用户 Word 模板时优先适配；没有则自动调用模板库。"],
  ["实验步骤", "把实验环境、数据准备、流程和复现方法单独输出成文档。"],
  ["代码骨架", "面向算法论文生成标准代码目录、README 和最小可运行示例。"],
  ["答辩材料", "同步生成答辩 PPT 结构和交付文件，减少后期整理成本。"],
];

export function FeatureGrid() {
  return (
    <section className="section">
      <div className="section__heading">
        <p className="eyebrow">Capabilities</p>
        <h2>围绕论文交付，而不是只生成一段文字。</h2>
      </div>
      <div className="feature-grid">
        {features.map(([title, desc]) => (
          <article key={title} className="feature-card glass-card">
            <h3>{title}</h3>
            <p>{desc}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
