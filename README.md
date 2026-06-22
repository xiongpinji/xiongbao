# X-Agent (开源重构版)

> 面向企业的自主智能体框架 —— **编排内核 + 适配层 + 独有语义**，底座全部采用 MIT/Apache 开源组件。

这是 X-Agent 的全新净重写版本。设计原则：不重复造轮子，把成熟能力（LLM 路由、记忆、可观测、沙箱、编排、SSO、授权、MCP）交给生产级开源组件，X-Agent 只保留并强化自己的差异化语义（工作流结构化视图、短剧工厂、开源候选发现、多租户审计黑板）。

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

### 方式 B：Docker Compose（full 模式）

```bash
cd deploy/compose
cp .env.example .env          # 按需填 LLM 配置
docker compose up -d
```

## 前端工作台（2026-06-22 起 ZCode 风格重构）

前端已重构为 **ZCode 风格暗色折叠 AI 工作台**：

- 主导航默认折叠，仅保留：新建任务 / 搜索 / 技能 / 对话 / 智能体 / 短剧工厂 / 工作流 / 设置。
- 知识库、开源发现迁入 **设置 → 索引库**；视频剪辑合并进短剧工厂的 **剪辑节点 / 导出节点**。
- 短剧工厂升级为 **自由拖拽画布工作流系统**：右键添加 11 类短剧节点，节点连线即工作流 `depends_on`，「运行画布」触发真实 `WorkflowEngine`，关键帧 / 视频走 `media task` 轮询，剪辑 / 导出走真实 timeline API；`/editor` 保留为 `?timeline_id=` 高级模式。

详见：

- `docs/frontend-zcode-workbench-refactor.md`（设计文档）
- `docs/coordination/`（多会话协作总控、handoff、report）
- `docs/coordination/reports/delivery-report.md`（本轮交付报告）

## 开发阶段


- **Phase 0**（当前）：脚手架 + 单机可启动 + LLM/trace/向量 三链路打通
- Phase 1：编排(LangGraph) + 记忆(Mem0) + MCP + 鉴权/租户隔离
- Phase 2：工作流(Temporal) + 浏览器/桌面/编码三类执行 agent
- Phase 3：短剧工厂 + 多模态 + 开源发现 + 插件单内核
- Phase 4：React 前端 + Tauri 桌面
- Phase 5：企业硬化 + 计费 + 交付

详见 `docs/ARCHITECTURE.md` 与 `docs/ROADMAP.md`。

> **接续开发请先读 [`docs/项目总览与开发指南.md`](docs/项目总览与开发指南.md)** —— 项目唯一权威入口（功能版图 / 架构 / 技术栈映射 / 开发约定 / 进度）。

## License

Apache-2.0
