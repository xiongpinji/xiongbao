# X-Agent 架构说明（重构版）

本文件描述 X-Agent 开源重构版的目标架构。核心理念：**编排内核 + 适配层 + 独有语义**。

## 设计原则

1. **不重复造轮子**：成熟能力交给生产级开源组件，通过 `adapters/` 薄封装接入，可替换。
2. **依赖倒置**：`core/` 与 `domains/` 只依赖 `adapters/` 暴露的 **Protocol 抽象接口**，不直接依赖具体开源库。这样底座可在 lite / full 模式间切换，也便于测试 mock。
3. **薄路由**：`api/` 只做请求校验、鉴权、租户隔离、调用 core/domains，不写业务逻辑。
4. **默认安全**：所有端点默认要求 principal（认证主体）+ 租户隔离，闭合旧版 30+ 越权问题。
5. **许可证合规**：只用 MIT/Apache/BSD。媒体（图像/视频）生成统一走**云端 AI 生成平台 API**（LibLib/LibTV 风格：选模型/LoRA → 提交任务 → 轮询取结果），不自托管 ComfyUI，规避 GPL-3.0 风险。

## 分层

```
apps/api/xagent/
├── main.py            # FastAPI 应用装配（lifespan + 中间件 + 路由）
├── infra/             # 横切基础设施
│   ├── settings.py    # pydantic-settings，XAGENT_* 环境变量
│   ├── db.py          # SQLAlchemy 2.0 async engine + session
│   ├── cache.py       # Redis 客户端（可降级 in-memory）
│   ├── logging.py     # 结构化日志
│   └── health.py      # liveness/readiness 依赖探活
├── adapters/          # 开源底座适配（每个子包定义 Protocol + 具体实现 + 工厂）
│   ├── llm/           # LiteLLM
│   ├── memory/        # Mem0 + Graphiti + Qdrant
│   ├── observability/ # Langfuse + OpenTelemetry
│   ├── sandbox/       # E2B / docker
│   ├── browser/       # browser-use
│   ├── desktop_auto/  # UI-TARS
│   ├── coding/        # OpenHands
│   ├── mcp/           # 官方 MCP SDK + ContextForge
│   └── tools/         # Composio
├── core/              # 编排内核（独有语义）
│   ├── orchestration/ # LangGraph 状态图
│   ├── agents/        # 角色注册 / 能力匹配
│   └── workflow/      # ★工作流结构化视图 + Temporal 桥接
├── domains/           # X-Agent 独有业务
│   ├── creative_studio/      # 短剧工厂（媒体生成走云 AI 生成 API，LibLib/LibTV 风格）
│   ├── open_source_discovery/# 开源候选发现
│   └── billing/              # 计费 / 订阅
├── enterprise/        # RBAC / SSO / 审计 / 多租户
│   ├── auth/          # Keycloak / 内置 JWT
│   ├── authz/         # Casbin / OpenFGA / OPA
│   └── audit/         # 防篡改审计链
└── api/               # FastAPI 路由（薄，按域分组）
```

## 运行模式

| 模式 | 说明 | 依赖 |
|---|---|---|
| **lite** | 单机 / 桌面 / 演示。SQLite + 内存缓存 + Qdrant 内存模式 + 内置 JWT 鉴权 | 无需 Docker |
| **full** | 单机生产 / 试点。Postgres + Redis + Qdrant + Langfuse + LiteLLM + Keycloak | docker-compose |
| **enterprise** | 多区域 HA（后做） | K8s / Helm |

模式由 `XAGENT_MODE` 环境变量控制；adapters 工厂据此选择具体实现或降级回退。

## 适配器契约模式

每个 adapter 子包遵循统一结构：

```python
# adapters/<name>/base.py     —— Protocol 抽象接口
# adapters/<name>/<impl>.py   —— 具体开源实现（如 litellm.py）
# adapters/<name>/null.py     —— lite/测试用空实现或降级实现
# adapters/<name>/factory.py  —— 据 settings 返回实例
```

`core` / `domains` 通过依赖注入拿到 Protocol，不感知具体实现。

## 三链路（Phase 0 验收）

1. **LLM 调用链**：`adapters.llm.factory.get_llm_client()` → LiteLLM → provider
2. **可观测链**：每次调用上报 Langfuse trace（OTel 兼容）
3. **记忆/向量链**：`adapters.memory` → Qdrant 写入/检索

Phase 0 完成标志：`scripts/smoke_three_chains.py` 三链路端到端通过。
