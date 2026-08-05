# X-Agent v1.0.0 Release Notes

> 首个正式发布版本 — 2026-08-05
> 合并主线：PR #7（merge commit `c2260cd`）+ 后续硬化提交，发布落点见 tag `v1.0.0`。
> 状态口径以 `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 为唯一事实源。

## 这是什么

X-Agent 是**可私有化交付的企业 AI Agent 平台**：Web 工作台 + REST API + CLI +
MCP 双传输，覆盖智能体运行、工作流编排、技能自进化、代码评审、企业级治理
（SSO/审计/权限）与运营自动化（告警/恢复/证据归档）全链路。

## 交付形态

- **Compose full**：`deploy/compose/`（Postgres + Redis + Qdrant + LiteLLM + Langfuse + 可观测栈）
- **Helm/K8s**：`deploy/helm/`，dev/staging/prod/enterprise 四套环境模板 + ESO secret 管理
- **GHCR 镜像**：`ghcr.io/xiongpinji/xiongbao/api` / `web`（`1.0.0` / `latest` / sha 三个 tag）
- **lite 单机**：SQLite + Ollama 本地模型，零 API 费用起步

## 本版本能力总览

**核心链路**
- 智能体编排（内置状态机 / LangGraph / DeerFlow 可插拔），多轮对话、SSE 流式、断点恢复
- 工作流引擎 + 可视化画布 + Run Console（失败原因/证据/建议动作结构化展示）
- 多 Agent 并行：进程内并行 + Supervisor 拓扑分发 + **git worktree 隔离执行**（v3 新增）
- 记忆/知识库（Qdrant 向量 + 语义检索）、开源发现、技能市场

**竞品对标能力（Roadmap v3，本版本新增）**
- AGENTS.md 三层分层指令（用户级 < 仓库根 < 子目录就近优先，Codex 语义对齐）
- 代码评审域：逻辑/安全/规范三维并行 + CLI + API + GitHub Action 模板
- 技能自进化：自动提炼 + 质量门禁 + **失败反思提炼** + **变体评测 + 人工审核队列**
- **SKILL.md 生态导入**（agentskills.io 格式，兼容 Hermes/Claude Code 技能库，强制门禁）
- **平台 MCP Server**：`xagent_run` / `xagent_code_review` / `xagent_skill_match` / `xagent_skill_import` 四工具，stdio + streamable HTTP 双传输，外部 agent 可直接调用

**企业级**
- SSO/OIDC（Keycloak）、JWT HS256/RS256、资源:动作粒度权限、API Key 管理
- 审计链（Postgres 持久化 + 完整性校验 + 导出）、多租户隔离
- 用户体系 DB 化（注册/改密/角色跨重启与多实例生效，v1.0.0 修复）

**运营自动化（Roadmap v2 P1）**
- Alertmanager 告警联动 → 证据落库；自动恢复引擎（LLM fallback / worker 重启 / DB 池回收）
- run/workflow 证据链自动生成 + 自动归档（tar.gz 含 manifest/审计/指标）
- 发布后观测自动汇总（HEALTHY / DEGRADED / ROLLBACK_RECOMMENDED 判定）

**平台化（Roadmap v2 P0）**
- secretRef / ESO（vault/aws/gcp/azure），生产 fail-fast
- 配置治理门禁：`validate_helm_values` 分级校验 + 环境差异策略机器校验 + CI `config-governance` job

## 质量证据（本版本发布依据）

- 后端全量 pytest：**670 通过 / 0 失败 / 10 跳过**（Docker 实机集成默认关闭）
- 前端：tsc 0 错误 / eslint 0 错误 / build 通过（路由级拆包，最大 chunk 294 kB）
- 远端 CI：master 全 8 job 绿（backend / frontend / license-gate / config-governance / e2e-api / docker-build / load-test / promptfoo-eval）
- 关键 E2E：full-flow 9/9（R13）；真实 LLM（Ollama）v3 全链路冒烟通过
- 压测：10min soak 无衰减；Postgres ≥ SQLite；canvas 4 worker 6.4× 扩展
- 多实例：共享状态（限流/登录锁/调度锁）+ 共享 DB 一致性 + JWT 无状态会话，同机两实例实测
- 安全：license gate 0 违规；危险默认值清零（P0-D）；生产配置 `validate_for_production()` 硬校验

## 本次发布不包含（边界，对外不可宣称）

- **短剧工厂行业交付**（已暂停，待整体移植；creative-studio 画布为活跃迭代区域，非本版本验收链路）
- 多机 HA / Redis 自身高可用（共享状态类为同机两实例实测）
- L2 E2B 云沙箱（无 key 未实测）
- 非当前机器的目标环境演练（首个客户环境需按试点包 Gate 复演）
- SaaS 级并发承诺（容量结论限单机/4 worker 基线）

## 升级与回滚

见 `docs/RELEASE_RUNBOOK_V1.md`；DB 迁移 `alembic upgrade head`（含本版本新增
`20260805_users_persist`，列级存在性检查，存量库安全）。

## 已知问题

见 `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`。
