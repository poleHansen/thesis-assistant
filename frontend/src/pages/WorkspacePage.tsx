import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ProjectForm } from "../components/ProjectForm";
import { createProject, listProjects } from "../lib/api";
import { statusText } from "../lib/format";
import type { ProjectCreate } from "../lib/types";

export function WorkspacePage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const createMutation = useMutation({
    mutationFn: (payload: ProjectCreate) => createProject(payload),
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${data.project_id}`);
    },
  });

  return (
    <div className="page page--workspace">
      <section className="page__hero">
        <p className="eyebrow">Workspace</p>
        <h1>创建项目，并把论文流程组织成一个可追踪工作台。</h1>
      </section>

      <div className="workspace-layout">
        <ProjectForm
          onSubmit={async (payload) => {
            await createMutation.mutateAsync(payload);
          }}
          loading={createMutation.isPending}
        />

        <section className="panel glass-card">
          <div className="panel__header">
            <div>
              <p className="eyebrow">Projects</p>
              <h3>已有项目</h3>
            </div>
          </div>
          {projectsQuery.isLoading ? <p className="muted">正在加载项目列表...</p> : null}
          {projectsQuery.isError ? (
            <p className="error-text">项目列表加载失败，请确认后端服务已启动。</p>
          ) : null}
          <div className="project-list">
            {projectsQuery.data?.map((project) => (
              <button
                key={project.project_id}
                className="project-list__item"
                onClick={() => navigate(`/projects/${project.project_id}`)}
              >
                <div>
                  <strong>{project.project_id}</strong>
                  <p>{project.updated_at}</p>
                </div>
                <span className={`status-pill status-pill--${project.status}`}>
                  {statusText[project.status]}
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
