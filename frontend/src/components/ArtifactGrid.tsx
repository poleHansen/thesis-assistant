import { getArtifactDownloadUrl } from "../lib/api";
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
              <a
                className="button button--ghost"
                href={getArtifactDownloadUrl(projectId, key)}
                target="_blank"
                rel="noreferrer"
              >
                下载
              </a>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
