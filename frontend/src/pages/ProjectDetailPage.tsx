import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { ArtifactGrid } from "../components/ArtifactGrid";
import { ExecutionTimeline } from "../components/ExecutionTimeline";
import { ExperimentSummary } from "../components/ExperimentSummary";
import { InnovationList } from "../components/InnovationList";
import { RunStatusCard } from "../components/RunStatusCard";
import { UploadDropzone } from "../components/UploadDropzone";
import { getProject, getProjectWorkflow, repairProject, runProject, uploadProjectFile } from "../lib/api";
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

  const workflowQuery = useQuery({
    queryKey: ["project-workflow", projectId],
    queryFn: () => getProjectWorkflow(projectId),
    enabled: Boolean(projectId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 3000 : false,
  });

  const repairMutation = useMutation({
    mutationFn: () => repairProject(projectId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["project-workflow", projectId] });
    },
  });

  const project = projectQuery.data;
  const workflow = workflowQuery.data;
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
  const resultTables = project?.result_schema.result_tables ?? [];
  const resultFigures = project?.result_schema.result_figures ?? [];
  const resultFindings = project?.result_schema.result_key_findings ?? [];
  const consistencyChecks = project?.result_schema.consistency_summary?.checks ?? [];
  const pptMappingEntries = project?.result_schema.ppt_section_mapping
    ? Object.entries(project.result_schema.ppt_section_mapping)
    : [];

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
                repairing={repairMutation.isPending}
                hasBlockingFindings={Boolean((workflow?.blocking_findings ?? project.result_schema.consistency_summary?.findings?.filter((item) => item.blocking) ?? []).length)}
                onRun={async () => {
                  await runMutation.mutateAsync();
                }}
                onRepair={async () => {
                  await repairMutation.mutateAsync();
                }}
              />
              <ExecutionTimeline
                logs={project.execution_log}
                warnings={project.warnings}
                auditTrail={workflow?.audit_trail ?? project.audit_trail}
                rollbackHistory={workflow?.rollback_history ?? project.rollback_history}
                nodeRuns={workflow?.node_runs ?? project.node_runs}
                checkpoints={workflow?.checkpoints ?? project.checkpoints}
                blockingFindings={workflow?.blocking_findings ?? project.result_schema.consistency_summary?.findings?.filter((item) => item.blocking) ?? []}
              />
            </div>

            <div className="project-layout__right">
              <ArtifactGrid artifacts={project.artifacts} projectId={projectId} />
              <InnovationList
                innovations={project.innovation_candidates}
                selectedClaim={project.selected_innovation?.claim}
                gapAnalysis={project.result_schema.gap_analysis}
                gapOverview={typeof project.result_schema.gap_analysis_overview === "string" ? project.result_schema.gap_analysis_overview : undefined}
                recommendation={project.result_schema.innovation_recommendation}
              />
              <ExperimentSummary plan={project.experiment_plan} />
              <section className="panel glass-card">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">Milestone Three</p>
                    {typeof project.result_schema.remediation_summary === "object" && project.result_schema.remediation_summary ? (
                      <article className="paper-card">
                        <strong>自动修复摘要</strong>
                        <div className="stack-list">
                          <small>已应用：{project.result_schema.remediation_summary.applied ? "是" : "否"}</small>
                          {project.result_schema.remediation_summary.actions?.map((action) => (
                            <small key={`${action.key}-${action.status}`}>
                              {action.key} / {action.status} / {action.message}
                            </small>
                          ))}
                        </div>
                      </article>
                    ) : null}
                    <h3>实现层与交付层摘要</h3>
                  </div>
                </div>
                <div className="stack-list">
                  <article className="paper-card">
                    <strong>结果分析摘要</strong>
                    <p>
                      {typeof project.result_schema.result_analysis_text === "string" &&
                      project.result_schema.result_analysis_text
                        ? project.result_schema.result_analysis_text
                        : "运行后会展示主结果、消融和论文/PPT 复用摘要。"}
                    </p>
                    {resultFindings.length > 0 ? (
                      <div className="paper-card__details">
                        <small>关键发现</small>
                        <ul className="result-list">
                          {resultFindings.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </article>
                  <article className="paper-card">
                    <strong>结果表与图表说明</strong>
                    {resultTables.length === 0 && resultFigures.length === 0 ? (
                      <p className="muted">运行后会展示主结果表、消融表、训练曲线和对比图说明。</p>
                    ) : (
                      <div className="stack-list">
                        {resultTables.map((table, index) => (
                          <div key={`${table.title ?? table.name ?? "table"}-${index}`} className="result-block">
                            <div className="paper-card__meta-row">
                              <span className="paper-card__badge">表格</span>
                              <strong>{table.title ?? table.name ?? `结果表 ${index + 1}`}</strong>
                            </div>
                            {table.summary ? <p>{table.summary}</p> : null}
                            {table.columns?.length ? <small>字段：{table.columns.join("、")}</small> : null}
                            {table.rows?.[0] ? (
                              <small>
                                示例：
                                {Object.entries(table.rows[0])
                                  .map(([key, value]) => `${key}=${value}`)
                                  .join("；")}
                              </small>
                            ) : null}
                          </div>
                        ))}
                        {resultFigures.map((figure, index) => (
                          <div key={`${figure.title ?? figure.name ?? "figure"}-${index}`} className="result-block">
                            <div className="paper-card__meta-row">
                              <span className="paper-card__badge">图表</span>
                              <strong>{figure.title ?? figure.name ?? `结果图 ${index + 1}`}</strong>
                            </div>
                            {figure.caption ? <p>{figure.caption}</p> : null}
                            {figure.insight ? <small>分析：{figure.insight}</small> : null}
                          </div>
                        ))}
                      </div>
                    )}
                  </article>
                  <article className="paper-card">
                    <strong>一致性检查</strong>
                    {project.result_schema.consistency_summary ? (
                      <div className="stack-list">
                        <div className="paper-card__meta-row">
                          <span className="paper-card__badge">
                            已对齐 {project.result_schema.consistency_summary.aligned_count ?? 0}/{project.result_schema.consistency_summary.total_checks ?? 0}
                          </span>
                          <span className={`paper-card__badge ${(project.result_schema.consistency_summary.blocking_count ?? 0) > 0 ? "paper-card__badge--warning" : ""}`}>
                            阻塞项 {project.result_schema.consistency_summary.blocking_count ?? 0}
                          </span>
                        </div>
                        {consistencyChecks.length > 0 ? (
                          <div className="consistency-grid">
                            {consistencyChecks.map((check) => (
                              <div key={check.key} className="consistency-item">
                                <div className="paper-card__meta-row">
                                  <span className={`paper-card__badge ${check.aligned ? "" : "paper-card__badge--warning"}`}>
                                    {check.aligned ? "已对齐" : "待复核"}
                                  </span>
                                  <strong>{check.label}</strong>
                                </div>
                                <small>{check.detail}</small>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {project.result_schema.consistency_summary.findings?.length ? (
                          <div className="stack-list">
                            {project.result_schema.consistency_summary.findings.map((item) => (
                              <div key={`${item.key}-${item.source}-${item.target}`} className="result-block">
                                <div className="paper-card__meta-row">
                                  <span className={`paper-card__badge ${item.aligned ? "" : "paper-card__badge--warning"}`}>
                                    {item.blocking ? "阻塞" : item.severity}
                                  </span>
                                  <strong>{item.label}</strong>
                                </div>
                                <small>{item.detail}</small>
                                {!item.aligned ? <p>{item.recommendation}</p> : null}
                                {item.diffs?.length ? (
                                  <div className="stack-list">
                                    {item.diffs.map((diff, index) => (
                                      <small key={`${item.key}-diff-${index}`}>
                                        {diff.field} / 期望：{diff.expected} / 实际：{diff.actual}
                                      </small>
                                    ))}
                                  </div>
                                ) : null}
                                {item.locations?.length ? (
                                  <div className="stack-list">
                                    {item.locations.map((location, index) => (
                                      <small key={`${item.key}-location-${index}`}>
                                        {location.label}（{location.path}）：{location.snippet}
                                      </small>
                                    ))}
                                  </div>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {project.result_schema.consistency_summary.warnings?.map((warning) => (
                          <p key={warning} className="muted">
                            {warning}
                          </p>
                        ))}
                      </div>
                    ) : (
                      <p className="muted">运行后会展示步骤、代码、论文之间的基础一致性状态。</p>
                    )}
                  </article>
                  <article className="paper-card">
                    <strong>论文 / PPT 映射</strong>
                    {pptMappingEntries.length === 0 ? (
                      <p className="muted">运行后会展示方法、实验、结果、结论页面与论文章节的映射关系。</p>
                    ) : (
                      <div className="stack-list">
                        {pptMappingEntries.map(([slide, section]) => (
                          <div key={`${slide}-${section}`} className="mapping-row">
                            <span>{slide}</span>
                            <small>{section}</small>
                          </div>
                        ))}
                      </div>
                    )}
                  </article>
                </div>
              </section>
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
              <section className="panel glass-card panel--scrollable panel--scrollable-literature">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">Literature</p>
                    <h3>文献摘要</h3>
                  </div>
                </div>
                <div className="stack-list panel__content-scroll">
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
