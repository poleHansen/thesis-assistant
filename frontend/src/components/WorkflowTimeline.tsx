const steps = [
  "输入研究方向",
  "检索文献与上传 PDF",
  "分析研究空白与候选创新点",
  "生成实验设计与实验步骤",
  "输出代码骨架与论文章节",
  "按模板生成论文与答辩 PPT",
];

export function WorkflowTimeline() {
  return (
    <section className="section section--alt" id="workflow">
      <div className="section__heading">
        <p className="eyebrow">Workflow</p>
        <h2>像产品一样推进论文流程，像科研一样保留证据链。</h2>
      </div>
      <div className="timeline">
        {steps.map((step, index) => (
          <div key={step} className="timeline__item glass-card">
            <span className="timeline__index">0{index + 1}</span>
            <p>{step}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
