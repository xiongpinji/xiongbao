# X-Agent 路线图

> 当前发布 / 商用 readiness 判断以 [`COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`](COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md) 为准。本文用于区分历史阶段、当前收口项和后续增强；不作为正式 GA 结论。

## 1. 历史功能阶段

Phase 0-5 表示代码骨架、接入点和本地能力链路的历史建设路线，不等同于当前正式商用封板。

| 阶段 | 历史目标 | 当前口径 |
|---|---|---|
| Phase 0 | 脚手架、配置、健康探针、LLM/trace/向量三链路 | 历史已实现 |
| Phase 1 | LangGraph 编排、记忆、MCP、鉴权/租户隔离 | 历史已实现 |
| Phase 2 | 工作流、浏览器/桌面/编码执行 agent | 历史已实现 |
| Phase 3 | 短剧工厂、多模态、开源发现、插件单内核 | 历史已实现 |
| Phase 4 | React 前端工作台、Tauri 桌面壳 | 历史已实现 |
| Phase 5 | 企业硬化、计费、部署交付骨架 | 历史已实现 |

## 2. 当前 readiness 收口（2026-08-03 刷新）

已完成或进入 Review 的证据项以 `docs/coordination/TASK_BOARD.md` 和 `docs/coordination/reports/delivery-report.md` 为准。

### 2.1 商用成熟度阶段映射

> 2026-07-26 起以 `COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 口径为准：G1/G2/G3 已全部完成，当前处于 Roadmap v2 增强期（详见 SOT §7）。本节保留下方历史收口记录作为阶段档案，不再作为当前 gate 判断依据。

- G1（内部试点可稳定使用）：**已完成**
- G2（正式商用 GA）：**已完成**
- G3（企业级长期运营治理与首轮验证）：**已完成**
- 当前阶段：**Roadmap v2 增强期**（P0 平台化与 P2 容量实证已于 2026-08-03 落地实测，见 SOT §4.1）

### 2.2 历史收口档案（2026-07-06 时点）

| 任务 | 当前口径 |
|---|---|
| P0-A 到 P0-E | 已在任务板 DONE，覆盖 orchestration await bug、前端 lint、demo/fallback 清理、危险默认值、CI 最小门禁 |
| R2 | DONE：前端 lint/typecheck/build 本地可复现，CI build 门禁已补入 |
| R3 | DONE：关键 E2E 冒烟包与 canvas run 持久化回归已补 |
| R6 | DONE：发布/回滚 Runbook v1 已补 |
| R7 | DONE：环境基线与 secret 注入说明已补 |
| R8 | DONE（2026-08-03 验收）：对外口径一致性终检记录与当前任务板状态对齐 |
| R9 | DONE：关键页面截图 / 验收记录已补齐 |
| R10 | DONE：full-flow E2E selector 漂移已修正；R13 已承接并修复 Chat SSE 完成态阻断 |
| R11 | DONE：npm audit / Vite chunk warning 风险已拆解；生产依赖 audit 为 0，全量 dev-build 工具链风险未清零 |
| R12 | DONE：SQLite/Alembic `0007` 历史本地库漂移已诊断；fresh DB 迁移到当前 head `0005` 通过 |
| R13 | DONE：Chat SSE 完成态 / fallback / 主区 runId 渲染已修复；本地 full-flow 9/9 通过 |
| R14 | DONE（2026-08-03 验收）：Vite chunk warning 已通过路由级懒加载拆包清除 |
| R15 | DONE（2026-08-03 验收）：任务板、delivery-report 与 R8 审计记录的状态 / 证据口径已同步 |
| R16 | DONE（2026-08-03 验收）：full-mode 演练前置清单已补齐；2026-08-03 增补 secretRef 注入路径（§8） |
| R17 | DONE（2026-08-03 验收）：PR 证据矩阵源数据已汇总为 R5 输入；2026-08-03 刷新附录见 `R17_EVIDENCE_MATRIX_REFRESH_20260803.md` |
| R18/R19 | DONE（2026-08-03 验收）：候选新鲜度审计 / secret 交接模板 |

发布准备项状态（2026-08-03）：

- R4 目标环境演练：当前机器等价环境实跑 DONE（R31）；非当前机器目标环境演练仍为发布 owner 决策项。
- R5 PR 审查包：已组装并刷新 v2（新候选 + CI 30834318982 全绿）；新候选已获 owner 签发（2026-08-03，R5 包 §0.4）。
- R8/R14/R15/R16/R17/R18/R19：全部 DONE（2026-08-03 依据 REVIEW_ACCEPTANCE_PACKET_20260803 验收）。

## 3. 进入 PR 审查前的最低条件

- 远端 CI 当前候选全绿。
- `apps/web` 前端 `lint`、`typecheck`、`build` 可复现。
- 关键 E2E 冒烟证据可映射到发布检查表。
- 发布/回滚 Runbook、环境基线、secret 注入说明可被 reviewer 找到。
- 目标环境演练结果、异常和回滚/处置证据归档。
- PR 描述包含风险摘要、验证矩阵、证据链接和 reviewer 关注点。

## 4. 后续增强方向

这些项目不阻塞当前 PR 审查准备，必须另建任务包推进：

- K8s/HA 与真实 secret manager / secretRef 演练。
- 完整 full-flow E2E 与长稳压测。
- 计费、审计、租户隔离的更大规模场景验证。
- 桌面壳打包、签名和分发验证。

## 5. 不可对外表述（2026-08-03 收窄）

按 SOT（2026-07-26）口径，项目已可按「正式商用可交付」对外表述。但以下事项仍**不可**宣称：

- 已完成多机 HA / K8s 生产级验证（共享状态类能力——限流/登录锁定/调度锁——已同机两实例实测，见 audit-20260802/HA_MULTI_INSTANCE_VERIFY_20260803.md；多机与 Redis 自身 HA 未演练）。
- L2 E2B 云沙箱已实测可用（代码就绪，无 key 未实测）。
- 已完成非当前机器的客户目标环境演练（当前机器等价演练 DONE，客户现场未做）。
- SaaS 级并发容量承诺（仅有单机基线与 4 worker 形态实测）。
