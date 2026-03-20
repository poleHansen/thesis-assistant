import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { ArtifactGrid } from "../components/ArtifactGrid";
import { ExecutionTimeline } from "../components/ExecutionTimeline";
import { ExperimentSummary } from "../components/ExperimentSummary";
import { InnovationList } from "../components/InnovationList";
import { RunStatusCard } from "../components/RunStatusCard";
import { UploadDropzone } from "../components/UploadDropzone";
import { getProject, runProject, uploadProjectFile } from "../lib/api";
import { templateSourceText } from "../lib/format";
import type { UploadKind } from "../lib/types";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 3000 : false,
  });

  const runMutation = useMutation({
    mutationFn: () => runProject(projectId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: ({ kind, file }: { kind: UploadKind; file: File }) =>
      uploadProjectFile(projectId, kind, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });

  const project = projectQuery.data;
  const templateSource = useMemo(() => {
    if (!project?.template_source) return "未选择模板";
    return templateSourceText[project.template_source.source_type];
  }, [project?.template_source]);
  const retrievalStatusText = useMemo(() => {
    switch (project?.retrieval_summary?.retrieval_status) {
      case "success":
        return "达标";
      case "partial":
        return "部分成功";
      case "fallback":
        return "离线回退";
      default:
        return "待运行";
    }
  }, [project?.retrieval_summary?.retrieval_status]);

  if (!projectId) {
    return (
      <div className="page">
        <p className="error-text">缺少项目 ID。</p>
      </div>
    );
  }

  return (
    <div className="page page--project">
      <section className="page__hero">
        <Link to="/workspace" className="back-link">
          返回工作台
        </Link>
        <p className="eyebrow">Project Workspace</p>
        <h1>{project?.request.topic ?? "项目详情"}</h1>
        <p className="page__subline">
          模板来源：<strong>{templateSource}</strong>
        </p>
      </section>

      {projectQuery.isLoading ? <p className="muted">正在加载项目详情...</p> : null}
      {projectQuery.isError ? (
        <p className="error-text">项目详情加载失败，请确认项目存在且后端服务可访问。</p>
      ) : null}

      {project ? (
        <>
          <div className="upload-grid">
            <UploadDropzone
              title="上传 Word 模板"
              description="请上传 .docx，并优先使用 {{cover.题目}}、{{section.摘要}} 这类占位符；若未上传，系统会自动使用内置模板。"
              accept=".docx"
              kind="word_template"
              onUpload={async (kind, file) => {
                await uploadMutation.mutateAsync({ kind, file });
              }}
              busy={uploadMutation.isPending}
            />
            <section className="panel glass-card">
              <div className="panel__header">
                <div>
                  <p className="eyebrow">Template Example</p>
                  <h3>用户模板示例说明</h3>
                </div>
              </div>
              <div className="stack-list">
                <p className="muted">推荐上传 .docx，并让每个占位符单独占一段。</p>
                <p>{"封面示例：{{cover.题目}}"}</p>
                <p>{"正文示例：先写一级标题“摘要”，下一段写 {{section.摘要}}"}</p>
                <p>{"章节示例：先写一级标题“第1章 绪论”，下一段写 {{section.第1章 绪论}}"}</p>
                <p className="muted">如果没有占位符，系统会回退为按一级标题定位插入。</p>
              </div>
            </section>
            <UploadDropzone
              title="上传答辩 PPT 模板"
              description="可选。不上传时，系统将自动使用内置模板。"
              accept=".ppt,.pptx"
              kind="ppt_template"
              onUpload={async (kind, file) => {
                await uploadMutation.mutateAsync({ kind, file });
              }}
              busy={uploadMutation.isPending}
            />
            <UploadDropzone
              title="上传论文 PDF"
              description="可补充高质量参考文献证据，用于综述和创新点分析。"
              accept=".pdf"
              kind="paper_pdf"
              onUpload={async (kind, file) => {
                await uploadMutation.mutateAsync({ kind, file });
              }}
              busy={uploadMutation.isPending}
            />
          </div>

          <div className="project-layout">
            <div className="project-layout__left">
              <RunStatusCard
                project={project}
                running={runMutation.isPending}
                onRun={async () => {
                  await runMutation.mutateAsync();
                }}
              />
              <ExecutionTimeline
                logs={project.execution_log}
                warnings={project.warnings}
              />
            </div>

            <div className="project-layout__right">
              <ArtifactGrid artifacts={project.artifacts} projectId={projectId} />
              <InnovationList
                innovations={project.innovation_candidates}
                selectedClaim={project.selected_innovation?.claim}
              />
              <section className="panel glass-card">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">Innovation Evidence</p>
                    <h3>创新点证据说明</h3>
                  </div>
                </div>
                <p className="muted">
                  当前候选创新点会标注 real / fallback。real 表示基于结构化文献差异分析生成，fallback 表示证据不足时的占位推荐，建议人工复核。
                </p>
                <p className="muted">
                  若推荐项显示为 fallback，优先补充文献后再进入实验设计；若显示为 real，可直接进入实验设计并继续完善对照实验。
                </p>
                <p className="muted">
                  卡片中的“分析依据 / 支撑证据 / 对照依据”来自结构化文献字段摘要；若为 fallback，这些区域可能为空。
                </p>
              </section>
              <ExperimentSummary plan={project.experiment_plan} />
              <section className="panel glass-card">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">Research Summary</p>
                    <h3>研究层状态摘要</h3>
                  </div>
                </div>
                <div className="stack-list">
                  <article className="paper-card">
                    <div className="paper-card__meta-row">
                      <span className="paper-card__badge">检索状态 {retrievalStatusText}</span>
                      <span className="paper-card__badge">
                        有效文献 {project.retrieval_summary?.valid_paper_count ?? 0}
                      </span>
                      <span className="paper-card__badge">
                        fallback {project.retrieval_summary?.fallback_count ?? 0}
                      </span>
                      <span className="paper-card__badge">
                        需复核 {project.retrieval_summary?.needs_review_count ?? 0}
                      </span>
                    </div>
                    {project.retrieval_summary?.failed_sources?.length ? (
                      <p className="muted">
                        失败源：{project.retrieval_summary.failed_sources.join("、")}
                      </p>
                    ) : (
                      <p className="muted">运行后将自动汇总有效文献数、fallback 数量和需复核数量。</p>
                    )}
                  </article>
                </div>
              </section>
              <section className="panel glass-card">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">Retrieval</p>
                    <h3>在线检索状态</h3>
                  </div>
                </div>
                <div className="stack-list">
                  {project.retrieval_diagnostics.length === 0 ? (
                    <p className="muted">运行后会展示 OpenAlex、arXiv、Semantic Scholar 等检索状态。</p>
                  ) : null}
                  {project.retrieval_diagnostics.map((item, index) => (
                    <article key={`${item.source}-${item.query}-${index}`} className="paper-card">
                      <strong>{item.source}</strong>
                      <span>
                        查询：{item.query} · 状态：{item.ok ? "成功" : "失败"} · 命中：{item.count}
                      </span>
                      {item.query_language ? <span>查询语言：{item.query_language}</span> : null}
                      {item.error ? <p className="error-text">失败原因：{item.error}</p> : null}
                    </article>
                  ))}
                </div>
              </section>
              <section className="panel glass-card">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">Literature</p>
                    <h3>文献摘要</h3>
                  </div>
                </div>
                <div className="stack-list">
                  {project.literature_records.length === 0 ? (
                    <p className="muted">运行后会展示已采集的文献记录。</p>
                  ) : null}
                  {project.literature_records.map((item) => (
                    <article key={`${item.title}-${item.year}`} className="paper-card">
                      <strong>{item.title}</strong>
                      <span>
                        {item.authors} · {item.year}
                      </span>
                      <div className="paper-card__meta-row">
                        <span className="paper-card__badge">排序 #{item.retrieval_rank || 0}</span>
                        <span className="paper-card__badge">来源 {item.source}</span>
                        <span className="paper-card__badge">证据 {item.evidence_source}</span>
                        <span className="paper-card__badge">
                          置信度 {item.confidence_score.toFixed(2)}
                        </span>
                        {item.evidence_source === "pdf" ? (
                          <span className="paper-card__badge">PDF 证据</span>
                        ) : null}
                        {item.evidence_source === "abstract" ? (
                          <span className="paper-card__badge">摘要证据</span>
                        ) : null}
                        {item.citation_count ? (
                          <span className="paper-card__badge">引用 {item.citation_count}</span>
                        ) : null}
                        {item.is_fallback ? (
                          <span className="paper-card__badge paper-card__badge--warning">
                            离线占位
                          </span>
                        ) : null}
                        {item.confidence_score < 0.55 ? (
                          <span className="paper-card__badge paper-card__badge--warning">低置信度</span>
                        ) : null}
                        {item.needs_review ? (
                          <span className="paper-card__badge paper-card__badge--warning">需复核</span>
                        ) : null}
                        {item.pdf_parse_status === "failed" ? (
                          <span className="paper-card__badge paper-card__badge--warning">PDF 失败</span>
                        ) : null}
                        {item.pdf_parse_status === "degraded" ? (
                          <span className="paper-card__badge paper-card__badge--warning">PDF 降级</span>
                        ) : null}
                      </div>
                      <p>{item.abstract}</p>
                      <div className="paper-card__details">
                        <p>
                          <strong>问题：</strong>
                          {item.problem}
                        </p>
                        <p>
                          <strong>方法：</strong>
                          {item.method}
                        </p>
                        <p>
                          <strong>数据集：</strong>
                          {item.dataset}
                        </p>
                        <p>
                          <strong>指标：</strong>
                          {item.metrics}
                        </p>
                        <p>
                          <strong>结论：</strong>
                          {item.conclusion}
                        </p>
                        <p>
                          <strong>局限：</strong>
                          {item.limitations}
                        </p>
                      </div>
                      {item.evidence_quote ? (
                        <blockquote className="paper-card__quote">{item.evidence_quote}</blockquote>
                      ) : null}
                      {item.review_note ? (
                        <p className="muted">复核建议：{item.review_note}</p>
                      ) : null}
                      {item.pdf_path ? <p className="muted">PDF 来源：{item.pdf_path}</p> : null}
                      {item.pdf_parse_message ? <p className="muted">PDF 状态：{item.pdf_parse_message}</p> : null}
                      {item.doi_or_url ? (
                        <a href={item.doi_or_url} target="_blank" rel="noreferrer">
                          查看来源
                        </a>
                      ) : null}
                    </article>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
