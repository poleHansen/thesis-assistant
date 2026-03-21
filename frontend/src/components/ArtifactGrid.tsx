import { downloadArtifact } from "../lib/api";
import { artifactDescriptions, artifactLabels } from "../lib/format";
import type { ArtifactBundle } from "../lib/types";

interface ArtifactGridProps {
  artifacts?: ArtifactBundle;
  projectId?: string;
}

export function ArtifactGrid({ artifacts, projectId }: ArtifactGridProps) {
  const entries = artifacts
    ? (Object.entries(artifacts).filter(([, value]) => Boolean(value)) as Array<
        [keyof ArtifactBundle, string]
      >)
    : [];

  const handleDownload = async (key: keyof ArtifactBundle) => {
    if (!projectId) {
      return;
    }
    try {
      await downloadArtifact(projectId, key);
    } catch (error) {
      const message = error instanceof Error ? error.message : "下载失败";
      window.alert(message);
    }
  };

  return (
    <section className="panel glass-card">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Artifacts</p>
          <h3>交付产物</h3>
        </div>
      </div>
      <div className="artifact-grid">
        {entries.length === 0 ? <p className="muted">项目尚未生成可下载产物。</p> : null}
        {entries.map(([key]) => (
          <article key={key} className="artifact-card">
            <div>
              <strong>{artifactLabels[key]}</strong>
              <p>{artifactDescriptions[key]}</p>
            </div>
            {projectId ? (
              <button
                type="button"
                className="button button--ghost"
                onClick={() => {
                  void handleDownload(key);
                }}
              >
                下载
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
