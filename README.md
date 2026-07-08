# X-Agent (开源重构版)

> 面向企业的自主智能体框架 —— **编排内核 + 适配层 + 独有语义**，底座全部采用 MIT/Apache 开源组件。

这是 X-Agent 的全新净重写版本。设计原则：不重复造轮子，把成熟能力（LLM 路由、记忆、可观测、沙箱、编排、SSO、授权、MCP）交给生产级开源组件，X-Agent 只保留并强化自己的差异化语义（工作流结构化视图、短剧工厂、开源候选发现、多租户审计黑板）。

## 当前状态口径（2026-07-06）

当前发布 / 商用 readiness 判断以 [`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`](docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md) 为准。项目主链可运行、功能版图完整，适合内部试点或受控私有部署；但尚未达到正式商用 GA，仍需远端 CI 全绿、目标环境演练、PR 审查包和发布签字。

如需查看当前候选可直接交付给管理员 / 运维 / 试点负责人的材料入口，请从 [`docs/DELIVERY_MATERIALS_INDEX_V1.md`](docs/DELIVERY_MATERIALS_INDEX_V1.md) 开始。

## 架构总览

```
xagent/
├── apps/
│   ├── api/          # FastAPI 后端：薄路由 + 编排内核(core) + 适配层(adapters) + 独有域(domains)
│   ├── worker/       # 后台任务 / 工作流 worker
│   ├── web/          # React18 + Vite + Tailwind 前端工作台
│   └── desktop/      # Tauri 桌面壳
├── deploy/
│   ├── compose/      # 单机 docker-compose（默认交付形态）
│   └── helm/         # K8s（占位）
├── packages/sdk-ts/  # TypeScript SDK
└── docs/
```

后端分层（`apps/api/xagent/`）：

| 层 | 职责 | 开源底座 |
|---|---|---|
| `core/` | 编排内核（独有语义） | LangGraph + Temporal |
| `adapters/llm` | LLM 网关 | LiteLLM |
| `adapters/memory` | 记忆 / RAG | Mem0 + Graphiti + Qdrant |
| `adapters/observability` | 追踪 / 评测 | Langfuse + OpenTelemetry |
| `adapters/sandbox` | 安全执行 | E2B / microsandbox (+docker 兜底) |
| `adapters/browser` | 浏览器自动化 | browser-use + Playwright |
| `adapters/desktop_auto` | 桌面 computer-use | UI-TARS |
| `adapters/coding` | 自主编码 | OpenHands |
| `adapters/mcp` | MCP 协议 / 网关 | 官方 MCP SDK + ContextForge |
| `adapters/tools` | 工具集成 | Composio |
| `domains/creative_studio` | 短剧工厂（护城河） | 云生成 API provider（LibLib/LibTV 风格）+ faster-whisper + Piper |
| `domains/open_source_discovery` | 开源候选发现（护城河） | 自研收敛 |
| `enterprise/` | RBAC/SSO/审计/多租户 | Keycloak + Casbin/OpenFGA/OPA |

## 许可证红线

避开 **AGPL**（Skyvern/Daytona）、**ELv2**（Arize Phoenix）、**Source-Available**（n8n/Pipedream）。媒体生成走云端 AI 生成平台 API（LibLib/LibTV 风格），**不自托管 ComfyUI，规避 GPL-3.0 风险**。CI 内置 license-check 门禁。

## 快速开始（单机）

### 方式 A：本地模型（零 API 费用，推荐）

```bash
# 0. 从 apps/api 目录启动（或显式补 PYTHONPATH）
# PowerShell: $env:PYTHONPATH = (Get-Location).Path
# Bash:       export PYTHONPATH="$PWD"

# 1. 安装 Ollama + 拉取模型
ollama pull qwen3:4b          # 或 qwen2.5:1.5b（更小更快）

# 2. 后端（指向本地 Ollama）
cd apps/api
pip install -e ".[dev]"
export XAGENT_LLM__OLLAMA_BASE_URL=http://localhost:11434
export XAGENT_LLM__OLLAMA_MODEL=qwen3:4b
export XAGENT_LLM__DEFAULT_MODEL=qwen3:4b
xagent serve                  # http://localhost:8000

# 3. 前端
cd ../web && npm install && npm run dev   # http://localhost:3000

# 4. 验证
xagent smoke                  # 三链路真实模型冒烟
curl localhost:8000/health
```

### 方式 B：Docker Compose（full 模式 / private deployment）

```bash
# 1. 先构建前端静态产物（compose 中 web 镜像直接复制 dist/）
cd apps/web
npm install
npm run build

# 2. 启动完整 unified runtime 主链
cd ../../deploy/compose
cp .env.example .env          # 按需填 LLM / JWT 配置
docker compose up -d --build

# 3. 验证核心入口
curl http://localhost:8000/health
curl http://localhost:8000/ready
# 浏览器打开 http://localhost:3000，提交任务后应跳转到 /runs/:runId
```

说明：

- compose 现在同时启动 `api`、`worker`、`web` 与所有依赖服务。
- `deploy/compose/postgres-init.sh` 会补建 `langfuse`、`contextforge`、`openfga` 数据库；如果你之前已经起过旧版 Postgres volume，需要先清理 volume 或手动补库。
- compose 中的 `XAGENT_CORS_ORIGINS` 现在直接复用 `.env` / `.env.example` 里的环境变量值；修改 `.env` 后重新 `docker compose up` 即可生效，不再被 compose 固定值覆盖。
- 当前 compose / LiteLLM 配置中已接通的 provider 路径以 OpenAI、DeepSeek 和宿主机 Ollama 为准；README / Runbook 不再宣称 compose 已直接打通 Anthropic provider。
- `worker` 负责 full 模式后台长任务；`/api/v1/runs/:run_id` 会把 task / workflow / creative 的统一读模型聚合到 Run Console。
- full / Celery 路径下，后台任务会先把最小元数据落到 `agent_tasks`，任务完成后再回写最终状态与结果，尽量保证重启后仍可续查；`GET /api/v1/tasks` 列表也会优先回查持久化状态，而不是长期显示 `pending`。
- compose 内默认通过 `host.docker.internal:11434` 访问宿主机 Ollama，并已为 `api` / `worker` 配置 `extra_hosts: ["host.docker.internal:host-gateway"]`，以兼容 Linux Docker 环境。
- 若后台任务仍在执行，Run Console 会通过 `delivery.resume` 暴露最小续航指针；审批型工作流会暴露审批续跑指针。
- 并行 worktree 开发时，可通过 `XAGENT_DEV_API_TARGET` 指向独立后端端口，再配合 `E2E_BASE_URL` 指向对应前端端口完成独立验收；例如前端 `4173` / 后端 `8100`。
- `apps/web/vite.config.ts` 默认读取 `XAGENT_DEV_API_TARGET`，未设置时回退到 `http://localhost:8000`。
- Playwright 使用 `E2E_BASE_URL` 指定前端地址，默认回退到 `http://localhost:3000`；full 模式验收账号必须通过 `E2E_USERNAME` / `E2E_PASSWORD` 显式提供。
- 后端测试建议从 `apps/api` 目录运行，或先设置 `PYTHONPATH=apps/api`，避免在仓库根直接执行时出现 `ModuleNotFoundError: xagent`。
- 详细部署与排障请看 [docs/DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md)。

## 前端工作台（2026-06-22 起 ZCode 风格重构）

前端已重构为 **ZCode 风格暗色折叠 AI 工作台**：

- 主导航默认折叠，仅保留：新建任务 / 搜索 / 技能 / 对话 / 智能体 / 短剧工厂 / 工作流 / 设置。
- 知识库、开源发现迁入 **设置 → 索引库**；视频剪辑合并进短剧工厂的 **剪辑节点 / 导出节点**。
- 短剧工厂升级为 **自由拖拽画布工作流系统**：右键添加 11 类短剧节点，节点连线即工作流 `depends_on`，「运行画布」触发真实 `WorkflowEngine`，关键帧 / 视频走 `media task` 轮询，剪辑 / 导出走真实 timeline API；`/editor` 保留为 `?timeline_id=` 高级模式。

详见：

- `docs/frontend-zcode-workbench-refactor.md`（设计文档）
- `docs/coordination/`（多会话协作总控、handoff、report）
- `docs/coordination/reports/delivery-report.md`（本轮交付报告）

## 历史阶段与当前收口

Phase 0-5 描述功能骨架与历史建设路线，不等同于当前正式 GA 结论。

- Phase 0：脚手架 + 单机可启动 + LLM/trace/向量三链路打通（历史已实现）
- Phase 1：编排(LangGraph) + 记忆(Mem0) + MCP + 鉴权/租户隔离（历史已实现）
- Phase 2：工作流(Temporal) + 浏览器/桌面/编码三类执行 agent（历史已实现）
- Phase 3：短剧工厂 + 多模态 + 开源发现 + 插件单内核（历史已实现）
- Phase 4：React 前端 + Tauri 桌面（历史已实现）
- Phase 5：企业硬化 + 计费 + 交付骨架（历史已实现）
- 当前收口：远端 CI、目标环境演练、PR 审查包、关键页面验收记录

详见 `docs/ARCHITECTURE.md`、`docs/ROADMAP.md` 与 `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`。

> **接续开发请先读 [`docs/项目总览与开发指南.md`](docs/项目总览与开发指南.md)** —— 功能版图 / 架构 / 技术栈映射 / 开发约定入口；当前发布状态以 [`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`](docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md) 为准。

## License

Apache-2.0
