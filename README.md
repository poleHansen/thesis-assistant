# thesis-assistant

本项目是一套面向毕业论文场景的智能体，你只需要输入研究方向，系统会自动生成一组结构化产物包括：

- 文献综述表
- 候选创新点报告
- 实验设计书
- 实验步骤文档
- 代码骨架压缩包
- 论文文档
- 答辩 PPT
- 审核与一致性报告

当前实现重点：

- `本地单用户 + 算法论文 MVP + DOCX 优先`
- 支持 `OpenAI`、`DeepSeek`、`Kimi/Moonshot` 的统一模型网关
- `有用户 Word 模板用用户模板；没有就自动使用模板库`
- 工作流采用 `LangGraphSupervisor` 抽象，默认稳定顺序执行，可通过环境变量开启 LangGraph 图执行
- 支持上传论文 PDF 作为补充证据源

## 项目结构

```text
app/
  main.py               FastAPI 入口
  workflow.py           Supervisor 与工作流主干
  agents.py             多智能体职责实现
  model_gateway.py      模型路由与 Provider Failover
  template_service.py   用户模板解析与模板库选择
  artifact_service.py   产物生成
  repository.py         SQLite 持久化
  storage.py            工作空间文件存储
tests/
  test_*.py             核心回归测试
```

## 安装

```bash
pip install -r requirements.txt
```

## 环境变量

可选 Provider Key，未配置时系统会自动回退到离线 `stub` 模式：

```bash
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
MOONSHOT_API_KEY=
THESIS_ASSISTANT_ENABLE_LANGGRAPH=0
THESIS_ASSISTANT_DATA_DIR=workspace
THESIS_ASSISTANT_DB_PATH=workspace/thesis_assistant.db
```

## 启动服务

```bash
uvicorn app.main:app --reload
```

默认会暴露这些接口：

- `POST /projects` 创建项目
- `POST /projects/{id}/files` 上传 `word_template` / `ppt_template` / `paper_pdf`
- `POST /projects/{id}/run` 执行多智能体流程
- `GET /projects/{id}` 查看项目状态
- `GET /projects/{id}/artifacts` 查看产物列表
- `GET /projects/{id}/artifacts/{artifact_name}` 下载产物

## 示例请求

### 1. 创建项目

```bash
curl -X POST http://127.0.0.1:8000/projects ^
  -H "Content-Type: application/json" ^
  -d "{\"topic\":\"中文文本分类算法\",\"paper_type\":\"algorithm\",\"need_code\":true,\"need_ppt\":true}"
```

### 2. 上传 Word 模板

```bash
curl -X POST http://127.0.0.1:8000/projects/<project_id>/files ^
  -F "kind=word_template" ^
  -F "file=@school-template.docx"
```

### 3. 运行工作流

```bash
curl -X POST http://127.0.0.1:8000/projects/<project_id>/run
```

## 当前实现说明

- 如果在线文献检索失败，系统会写入离线占位文献并继续流程，避免整条链路中断。
- 如果 `python-docx` / `python-pptx` / `openpyxl` 不可用，相关产物会自动回退到更轻量的文本格式。
- 默认模板库内置：
  - `通用本科论文`
  - `工科毕业论文`
  - `课程设计/实验报告型`
- `Word` 模板规则已经固定：
  - 用户上传模板时，优先解析并使用用户模板
  - 未上传模板时，自动从模板库选择默认模板

## 测试

```bash
python -m unittest discover -s tests -v
```
