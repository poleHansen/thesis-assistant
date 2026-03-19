import type { ArtifactBundle, ProjectStatus, TemplateSourceType } from "./types";

export const statusText: Record<ProjectStatus, string> = {
  created: "待开始",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

export const templateSourceText: Record<TemplateSourceType, string> = {
  user_upload: "用户上传模板",
  library_default: "模板库默认模板",
};

export const artifactLabels: Record<keyof ArtifactBundle, string> = {
  literature_review: "文献综述表",
  innovation_report: "创新点报告",
  experiment_plan: "实验设计书",
  procedure: "实验步骤文档",
  thesis_docx: "论文 Word",
  thesis_pdf: "论文 PDF",
  code_zip: "代码包",
  defense_pptx: "答辩 PPT",
  qa_report: "质检报告",
};

export const artifactDescriptions: Record<keyof ArtifactBundle, string> = {
  literature_review: "文献对比与综述汇总表",
  innovation_report: "创新点分析与候选报告",
  experiment_plan: "实验设计与评估计划",
  procedure: "实验步骤与复现实验文档",
  thesis_docx: "论文可编辑文档",
  thesis_pdf: "论文导出 PDF",
  code_zip: "项目代码与配置压缩包",
  defense_pptx: "答辩演示文稿",
  qa_report: "质量检查与一致性报告",
};

export function joinLines(values?: string[] | null) {
  return values && values.length > 0 ? values.join("、") : "暂无";
}
