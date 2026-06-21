# X-Agent 重构路线图

> 全功能一次到位，单机/桌面优先，底座全换开源。每阶段可独立验收。

## Phase 0 — 脚手架与底座（单机可启动）✅ 进行中

- [x] monorepo 骨架 + README / LICENSE / .gitignore
- [ ] `apps/api` pyproject + settings(XAGENT_*) + 配置体系
- [ ] infra：DB(SQLAlchemy2 + Alembic) / Redis / 结构化日志 / 健康探针
- [ ] FastAPI app 骨架 + `/health` `/ready` + 中间件（CORS/请求日志/租户隔离占位）
- [ ] adapters：llm(LiteLLM) / observability(Langfuse) / memory(Qdrant)，Protocol + 工厂 + lite 降级
- [ ] deploy/compose：docker-compose（postgres/redis/qdrant/langfuse/litellm）
- [ ] CI：ruff + mypy + pytest + **license-check 门禁**
- [ ] 三链路验收脚本 `scripts/smoke_three_chains.py`

**验收**：`docker compose up` 起依赖；`xagent serve` 启动；`/health` `/ready` 200；三链路脚本通过。

## Phase 1 — 编排与记忆内核

- [ ] LangGraph agent 状态机 + 角色注册 / 能力匹配
- [ ] Mem0 + Graphiti 记忆适配；向量统一走 Qdrant
- [ ] 官方 MCP SDK + 工具注册；ContextForge 网关接口
- [ ] 沙箱适配（docker 兜底 + E2B 接口）
- [ ] 鉴权中间件（内置 JWT / Keycloak）+ 租户隔离 + RBAC(Casbin)，**全端点强制 principal**

**验收**：单 agent run（LLM + 记忆读写 + 工具调用）端到端；越权回归全绿。

## Phase 2 — 工作流 + 自动化执行

- [ ] 工作流引擎（Temporal，lite 降级 Celery）+ 保留结构化 view model
- [ ] 浏览器 agent（browser-use）
- [ ] 桌面 agent（UI-TARS）
- [ ] 编码 agent（OpenHands，保留 PR 交付 / 审批语义）

**验收**：一个含补偿/审批/回放的 workflow 跑通；三类执行 agent 各跑通一个真实任务。

## Phase 3 — 独有域 + 多模态

- [ ] 短剧工厂移植（producer/storyboard/media/quality/prompt_compiler）
- [ ] 媒体生成 = 云 AI 生成 API provider（LibLib/LibTV 风格：选模型/LoRA → 提交生成任务 → 轮询取结果；可插拔图像/视频 provider）+ faster-whisper(STT) + Piper(TTS)
- [ ] 开源候选发现收敛（provider 去重 + 统一评分）
- [ ] 插件 / 技能单内核 + Composio 工具后端

**验收**：一句话 brief → 短剧生产工作流草稿 → 审核导出；开源发现多源聚合打分可用。

## Phase 4 — 前端 + 桌面

- [ ] React18 + Vite + Tailwind 工作台（react-router 替自研 hash 路由）
- [ ] 页面：对话/线程/任务/项目/短剧工厂(React Flow)/工作流/智能体/知识库/工具/数据/审计/自动化/设置
- [ ] SSE 流式 + WebSocket 实时
- [ ] Tauri 桌面壳

**验收**：前端全页面接真实后端；桌面应用可打包启动。

## Phase 5 — 企业硬化 + 计费 + 交付

- [ ] Keycloak SSO（realm = 租户）+ OpenFGA + OPA
- [ ] 防篡改审计链（HMAC 哈希链 + Postgres）
- [ ] 计费 / 订阅 / 合作伙伴
- [ ] 多租户隔离渗透测试；compose 交付 + 桌面打包 + 文档 + 迁移脚本

**验收**：越权 / 跨租户测试全绿；`docker compose up` 全功能可用；桌面可分发。
