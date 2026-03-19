import { FeatureGrid } from "../components/FeatureGrid";
import { HeroSection } from "../components/HeroSection";
import { ProviderStrip } from "../components/ProviderStrip";
import { WorkflowTimeline } from "../components/WorkflowTimeline";

export function HomePage() {
  return (
    <>
      <HeroSection />
      <FeatureGrid />
      <WorkflowTimeline />
      <section className="section">
        <div className="showcase">
          <div className="showcase__copy">
            <p className="eyebrow">Template Strategy</p>
            <h2>Word 模板优先适配，没给模板也能继续产出。</h2>
            <p>
              页面明确展示“用户模板优先，否则自动选择模板库”的策略，让项目从一开始就围绕交付标准组织，而不是最后再补格式。
            </p>
          </div>
          <div className="showcase__card glass-card">
            <div className="showcase__line">
              <strong>用户上传</strong>
              <span>学校模板 / 学院模板 / 指导老师模板</span>
            </div>
            <div className="showcase__line">
              <strong>默认兜底</strong>
              <span>通用本科 / 工科论文 / 课程设计模板库</span>
            </div>
            <div className="showcase__line">
              <strong>输出结果</strong>
              <span>论文 Word、论文 PDF、PPT、代码包、实验步骤</span>
            </div>
          </div>
        </div>
      </section>
      <ProviderStrip />
      <section className="section section--alt">
        <div className="section__heading">
          <p className="eyebrow">Deliverables</p>
          <h2>最终拿到的是一套交付包，而不是一段孤立文本。</h2>
        </div>
        <div className="deliverable-grid">
          {["论文终稿", "实验步骤", "代码包", "答辩 PPT", "审核报告"].map((item) => (
            <div key={item} className="deliverable-item glass-card">
              <strong>{item}</strong>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
