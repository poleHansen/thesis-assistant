import { useState } from "react";
import type { ProjectCreate } from "../lib/types";

interface ProjectFormProps {
  onSubmit: (payload: ProjectCreate) => Promise<void>;
  loading?: boolean;
}

const initialState: ProjectCreate = {
  topic: "",
  constraints: [],
  paper_type: "algorithm",
  language: "zh-CN",
  need_code: true,
  need_ppt: true,
  school_requirements: "",
  delivery_mode: "draft",
};

export function ProjectForm({ onSubmit, loading }: ProjectFormProps) {
  const [form, setForm] = useState<ProjectCreate>(initialState);
  const [constraintText, setConstraintText] = useState("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({
      ...form,
      constraints: constraintText
        .split(/\n|,|，/)
        .map((item) => item.trim())
        .filter(Boolean),
    });
  }

  return (
    <form className="panel glass-card form-grid" onSubmit={handleSubmit}>
      <div className="panel__header">
        <div>
          <p className="eyebrow">Create Project</p>
          <h3>创建一个新的论文项目</h3>
        </div>
      </div>

      <label className="field">
        <span>研究方向</span>
        <input
          value={form.topic}
          onChange={(event) => setForm({ ...form, topic: event.target.value })}
          placeholder="例如：基于中文文本分类的轻量化算法研究"
          required
        />
      </label>

      <label className="field">
        <span>论文类型</span>
        <select
          value={form.paper_type}
          onChange={(event) => setForm({ ...form, paper_type: event.target.value })}
        >
          <option value="algorithm">algorithm</option>
          <option value="system">system</option>
          <option value="experiment">experiment</option>
        </select>
      </label>

      <label className="field">
        <span>语言</span>
        <select
          value={form.language}
          onChange={(event) => setForm({ ...form, language: event.target.value })}
        >
          <option value="zh-CN">zh-CN</option>
          <option value="en-US">en-US</option>
        </select>
      </label>

      <label className="field">
        <span>学校要求</span>
        <textarea
          rows={3}
          value={form.school_requirements}
          onChange={(event) =>
            setForm({ ...form, school_requirements: event.target.value })
          }
          placeholder="例如：工科毕业论文，参考文献采用 GB/T 7714"
        />
      </label>

      <label className="field">
        <span>约束条件</span>
        <textarea
          rows={3}
          value={constraintText}
          onChange={(event) => setConstraintText(event.target.value)}
          placeholder="每行或逗号分隔：只能使用公开数据集、实验需在 CPU 环境可运行"
        />
      </label>

      <div className="toggle-row">
        <label className="toggle">
          <input
            type="checkbox"
            checked={form.need_code}
            onChange={(event) =>
              setForm({ ...form, need_code: event.target.checked })
            }
          />
          <span>生成代码骨架</span>
        </label>
        <label className="toggle">
          <input
            type="checkbox"
            checked={form.need_ppt}
            onChange={(event) =>
              setForm({ ...form, need_ppt: event.target.checked })
            }
          />
          <span>生成答辩 PPT</span>
        </label>
      </div>

      <button className="button button--primary" type="submit" disabled={loading}>
        {loading ? "创建中..." : "创建项目"}
      </button>
    </form>
  );
}
