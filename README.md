# thesis-assistant

本项目是一套面向毕业论文场景的多智能体平台。你输入研究方向后，系统会生成一组结构化交付物，包括：

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
- `有用户 Word 模板时优先使用用户模板；没有时自动使用模板库`
- 工作流采用 `LangGraphSupervisor` 抽象，默认稳定顺序执行，可通过环境变量启用 LangGraph 图执行
- 支持上传论文 PDF 作为补充证据源
- 已提供独立前端工程 `frontend/`，页面风格偏苹果官网式展示和工作台体验

## 推荐 Python 版本

推荐使用：

- `Python 3.11`

原因：

- 当前依赖组合对 `Python 3.11` 的兼容性最稳
- `fastapi`、`pydantic`、`langgraph`、`python-docx`、`python-pptx`、`openpyxl` 在 3.11 上更常见、更容易排查问题
- 你本机虽然可以有更高版本 Python，但项目环境建议单独固定到 `3.11`

如果必须扩展说明，当前项目更建议使用：

- 推荐：`Python 3.11`
- 可尝试：`Python 3.10 / 3.12`
- 不建议作为首选：`Python 3.13`

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

frontend/
  src/                  React + Vite 前端源码
  package.json          前端依赖与脚本

tests/
  test_*.py             核心回归测试
```

## 使用 conda 安装后端

### 1. 创建 conda 环境

```bash
conda create -n thesis-assistant python=3.11 -y
```

### 2. 激活环境

```bash
conda activate thesis-assistant
```

### 3. 进入项目目录

```bash
cd /d D:\code\thesis-assistant
```

如果你在 PowerShell 中，也可以直接：

```powershell
Set-Location D:\code\thesis-assistant
```

### 4. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

## 环境变量

可选 Provider Key。未配置时，系统会自动回退到离线 `stub` 模式：

```bash
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
MOONSHOT_API_KEY=
THESIS_ASSISTANT_ENABLE_LANGGRAPH=0
THESIS_ASSISTANT_DATA_DIR=workspace
THESIS_ASSISTANT_DB_PATH=workspace/thesis_assistant.db
```

Windows PowerShell 示例：

```powershell
$env:OPENAI_API_KEY="your_key"
$env:DEEPSEEK_API_KEY="your_key"
$env:MOONSHOT_API_KEY="your_key"
```

## 启动后端服务

确保你已经激活 conda 环境并位于项目根目录：

```bash
conda activate thesis-assistant
cd /d D:\code\thesis-assistant
uvicorn app.main:app --reload
```

启动后默认地址：

- 后端 API: `http://127.0.0.1:8000`
- 健康检查: `http://127.0.0.1:8000/health`

## 前端开发

项目已新增独立前端工程 `frontend/`，用于提供苹果官网风格的产品首页和项目工作台。

### 1. 安装 Node 依赖

```bash
cd /d D:\code\thesis-assistant\frontend
npm install
```

### 2. 启动前端开发服务

```bash
npm run dev
```

默认通过 Vite 代理把 `/api` 请求转发到：

- `http://127.0.0.1:8000`

前端页面包括：

- `/` 产品首页
- `/workspace` 项目列表和创建项目入口
- `/projects/:projectId` 项目工作台

### 3. 构建前端

```bash
npm run build
```

说明：

- 当前 `build` 使用 `vite build`
- 如需单独做 TypeScript 检查，可运行：

```bash
npm run typecheck
```

## 推荐的完整启动顺序

### 终端 1：启动后端

```bash
conda activate thesis-assistant
cd /d D:\code\thesis-assistant
uvicorn app.main:app --reload
```

### 终端 2：启动前端

```bash
cd /d D:\code\thesis-assistant\frontend
npm install
npm run dev
```

然后打开：

- `http://127.0.0.1:5173`

## 默认 API 接口

- `POST /projects` 创建项目
- `GET /projects` 获取项目列表
- `GET /projects/{id}` 查看项目详情
- `POST /projects/{id}/files` 上传 `word_template` / `ppt_template` / `paper_pdf`
- `POST /projects/{id}/run` 执行多智能体流程
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

- 如果在线文献检索失败，系统会写入离线占位文献并继续流程，避免整条链路中断
- 如果 `python-docx` / `python-pptx` / `openpyxl` 不可用，相关产物会自动回退到更轻量的文本格式
- 默认模板库内置：
  - `通用本科论文`
  - `工科毕业论文`
  - `课程设计/实验报告型`
- `Word` 模板规则已经固定：
  - 用户上传模板时，优先解析并使用用户模板
  - 未上传模板时，自动从模板库选择默认模板

## 测试

后端测试：

```bash
conda activate thesis-assistant
cd /d D:\code\thesis-assistant
python -m unittest discover -s tests -v
```

前端构建：

```bash
cd /d D:\code\thesis-assistant\frontend
npm run build
```
