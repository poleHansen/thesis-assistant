import { Link } from "react-router-dom";

export function HeroSection() {
  return (
    <section className="hero">
      <div className="hero__copy">
        <p className="eyebrow">Research to Thesis Agent System</p>
        <h1>
          从研究方向出发，
          <br />
          生成一套可交付的论文工作流。
        </h1>
        <p className="hero__lede">
          文献检索、创新点候选、实验设计、代码骨架、Word 模板输出与答辩
          PPT，在一个克制、清晰、可追踪的工作台中完成。
        </p>
        <div className="hero__actions">
          <Link to="/workspace" className="button button--primary">
            进入工作台
          </Link>
          <a href="#workflow" className="button button--ghost">
            查看流程
          </a>
        </div>
      </div>
      <div className="hero__panel glass-card">
        <div className="hero-demo__window">
          <div className="hero-demo__dots">
            <span />
            <span />
            <span />
          </div>
          <div className="hero-demo__content">
            <p className="hero-demo__label">研究方向</p>
            <div className="hero-demo__input">基于中文文本分类的轻量化算法研究</div>
            <div className="hero-demo__grid">
              <div className="hero-demo__card">
                <span>文献检索</span>
                <strong>OpenAlex / arXiv / PDF</strong>
              </div>
              <div className="hero-demo__card">
                <span>模板输出</span>
                <strong>用户模板优先</strong>
              </div>
              <div className="hero-demo__card">
                <span>大模型</span>
                <strong>OpenAI / DeepSeek / Kimi</strong>
              </div>
              <div className="hero-demo__card">
                <span>交付包</span>
                <strong>论文 + 代码 + PPT</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
