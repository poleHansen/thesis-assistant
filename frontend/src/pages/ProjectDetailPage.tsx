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
              description="学校模板优先适配。若不上传，系统会自动使用模板库。"
              accept=".doc,.docx"
              kind="word_template"
              onUpload={async (kind, file) => {
                await uploadMutation.mutateAsync({ kind, file });
              }}
              busy={uploadMutation.isPending}
            />
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
              <ExperimentSummary plan={project.experiment_plan} />
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
                      <p>{item.abstract}</p>
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
