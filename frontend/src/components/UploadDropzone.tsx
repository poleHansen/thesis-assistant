import type { UploadKind } from "../lib/types";

interface UploadDropzoneProps {
  title: string;
  description: string;
  accept?: string;
  kind: UploadKind;
  onUpload: (kind: UploadKind, file: File) => Promise<void>;
  busy?: boolean;
}

export function UploadDropzone({
  title,
  description,
  accept,
  kind,
  onUpload,
  busy,
}: UploadDropzoneProps) {
  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    await onUpload(kind, file);
    event.target.value = "";
  }

  return (
    <label className="upload-card glass-card">
      <span className="upload-card__title">{title}</span>
      <span className="upload-card__desc">{description}</span>
      <span className="upload-card__hint">
        {busy ? "上传中..." : "点击选择文件或拖拽到此区域"}
      </span>
      <input type="file" accept={accept} onChange={handleChange} disabled={busy} />
    </label>
  );
}
