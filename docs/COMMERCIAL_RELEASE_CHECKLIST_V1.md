# X-Agent 商用发布前检查表 v1

> 用途：在对外试点、内部验收、预发布或正式发布前，由发布负责人逐项打勾。若任一 **P0 阻断项** 未完成，则本次发布不得标记为“正式商用可交付”。
>
> **2026-07-06 readiness 预检口径：** 本轮 P0-A 到 P0-E 已补齐本地收口证据和最小 CI 基线；本检查表复选框仍是具体版本 / 具体环境的发布签字项，未产生版本号、Git tag、远端 CI 全绿记录和环境演练记录前，不得勾选为正式商用可交付。

---

## 一、版本与范围确认

- [ ] 本次发布有唯一版本号 / Git tag / 发布分支记录。
- [ ] 本次发布范围已冻结，未提交工作树不属于交付内容。
- [ ] 已明确本次交付包含哪些页面、接口、能力域。
- [ ] 已明确本次不包含哪些实验性或后续能力。
- [ ] `README.md`、`docs/ROADMAP.md`、`docs/项目总览与开发指南.md`、`docs/XIONG_BAO_接手与启动说明_2026-07-03.md` 的项目状态口径一致。
- [ ] 已存在唯一事实源文档：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`。

## 二、P0 阻断项（未完成不得正式发布）

### 2.1 文档与口径
- [ ] README 中不再出现与真实状态冲突的阶段描述。
- [ ] ROADMAP 已区分“历史已完成”和“当前仍在硬化”的内容。
- [ ] 对外口径已由 TL/Owner 审核通过。

### 2.2 前端首发范围
- [ ] 首发页面范围已冻结并文档化。
- [ ] 当前发布所需前端资源已纳入版本控制。
- [ ] 与发布无关的实验性页面/组件未混入正式发布包。
- [ ] 关键页面（登录、对话、工作流、Run Console、设置）已有截图或验收记录。

> R9 本地页面验收证据见 `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`；复选框仍保留为具体版本 / 具体环境的发布负责人签字项。

### 2.3 runtime 失败闭环
- [ ] direct run 失败时，运行详情可见失败原因。
- [ ] stream run 失败时，运行详情可见失败原因。
- [ ] workflow/task 失败时，Run Console 可见状态、证据、建议动作。
- [ ] 前端存在 blocked / failed / retryable 的明确展示，不是空白或静默失败。
- [ ] 至少完成一次“失败→定位→恢复/重试”的人工演练。

### 2.4 安全默认值
- [ ] 生产环境不允许使用默认 `admin/admin`。
- [ ] 生产环境不允许使用默认 JWT secret。
- [ ] `deploy/compose/docker-compose.yml` 中商用危险默认值已处理。
- [ ] `deploy/helm/values.yaml` 中 `change-me` 类占位已改为显式必填策略。
- [ ] `XAGENT_CORS_ORIGINS` 未包含 `*`。
- [ ] 已确认 `require_auth` 没有被关闭。
- [ ] Langfuse 默认账号密码已修改或禁用初始化默认用户。

### 2.5 发布与回滚
- [ ] 已存在 `docs/RELEASE_RUNBOOK_V1.md`。
- [ ] 已明确发布步骤、DB 迁移步骤、回滚步骤。
- [ ] 已在新环境或 staging 环境完整演练过一次。
- [ ] 演练过程中保留了日志、截图、结果记录。

> R12 SQLite/Alembic 漂移诊断见 `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`：当前迁移 head 为 `0005`，fresh SQLite 可迁移；旧本地 `apps/api/xagent.db` 为未知 revision `0007` 且缺 `evidence_records`，不得作为目标环境迁移通过证据。
>
> R16 full-mode 演练前置清单见 `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`：已整理 R4 恢复所需的 `LANGFUSE_*`、JWT secret、full-mode 显式账号、端口、依赖服务、LLM 路径和 compose config 预检；该清单不等于目标环境演练完成，以下复选框仍需 R4 实跑后签字。

### 2.6 CI 与质量门禁

> 最小 CI 基线：`.github/workflows/ci.yml` 至少包含 backend `ruff check xagent tests`、backend `pytest -q`、frontend `npm run lint`、frontend `npm run typecheck`、frontend `npm run build`。关键 Playwright E2E 仍是发布前门禁；当前工作树对应的远端 CI 绿色记录仍需单独补齐。
>
> R11 前端依赖 / 构建风险审计见 `docs/coordination/reports/R11_NPM_AUDIT_FRONTEND_BUILD_RISK.md`：`npm audit --omit=dev` 为 0；全量 `npm audit` 仍有 Vite / esbuild dev-build 工具链 1 moderate / 1 high。
>
> R14 Vite chunk warning 证据见 `docs/coordination/reports/R14_VITE_CHUNK_SPLIT.md`：通过路由级 `React.lazy` / `Suspense` 拆包，`npm run build` 已不再出现 chunk warning，最大 JS chunk 为 294.19 kB / gzip 96.09 kB；该证据不替代真实性能压测或 R4 目标环境演练。
>
> R13 Chat SSE / full-flow 证据见 `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`：本地 API 8000 + 当前仓库 Web 3100 下，`full-flow.spec.ts --project=chromium` 已 9/9 通过；该证据不替代 R4 目标环境演练或发布负责人签字。

- [ ] backend `pytest -q` 通过。
- [ ] backend `ruff check xagent tests` 通过。
- [ ] frontend `npm run typecheck` 通过。
- [ ] frontend `npm run build` 通过。
- [ ] frontend `npm run lint` 通过。
- [ ] 至少一组关键 Playwright E2E 已纳入发布前门禁并通过。
- [ ] 本次发布对应 CI 记录全部绿色。

---

## 三、功能与体验验收

### 3.1 基础链路
- [ ] `/health` 返回正常。
- [ ] `/ready` 返回正常。
- [ ] 登录链路可用。
- [ ] 登录后工作台首页无阻断报错。
- [ ] Run Console 可打开并展示运行详情。

### 3.2 核心能力
- [ ] 智能体运行链路可完成一次成功执行。
- [ ] 工作流创建/查看/审批链路可完成一次验证。
- [ ] 记忆/检索链路可完成一次验证。
- [ ] 开源发现链路可完成一次验证。
- [ ] 短剧工厂/画布链路可完成一次验证（若属于本次交付范围）。
- [ ] 设置页与关键系统配置展示无明显断链。

### 3.3 用户体验
- [ ] 空状态、失败态、加载态没有明显空白页或无说明崩溃。
- [ ] 错误提示可被用户理解，不是纯技术堆栈信息。
- [ ] 导航结构与首发版定义一致。
- [ ] 多语言/文案不会出现大面积未翻译或占位文本。

---

## 四、环境与配置基线

> 环境基线与 secret 注入说明见 `docs/ENVIRONMENT_BASELINE_V1.md`；以下复选框仍需按具体环境实测后由发布负责人勾选。

- [ ] 已区分 dev / staging / prod 配置。
- [ ] 关键 secret 来源清晰（env / secret manager / k8s secret）。
- [ ] 所有外部依赖地址与凭据已按环境配置。
- [ ] 生产环境已明确使用哪种 LLM 路径（OpenAI / DeepSeek / Ollama / LiteLLM）。
- [ ] 若启用 OIDC/Keycloak，JWKS 与 issuer 配置已验证。
- [ ] 若启用 OpenFGA/ContextForge，其健康状态已检查。
- [ ] 对象存储（如启用）已验证 put/get/delete。

---

## 五、安全与合规

- [ ] `python scripts/license_check.py` 通过。
- [ ] 安全扫描通过：`python tests/security/scan.py --host http://localhost:8000`。
- [ ] 跨租户访问防护已验证。
- [ ] 鉴权/权限不足场景返回符合预期。
- [ ] 安全响应头存在。
- [ ] 限流可触发并返回 429。
- [ ] 审计导出可执行。
- [ ] 已确认数据库、Redis、Qdrant 不直接公网裸露。
- [ ] HTTPS / TLS 终止方案已明确。

---

## 六、可观测与运维

- [ ] `/metrics` 可访问。
- [ ] Grafana 仪表板已导入或有等价监控视图。
- [ ] Langfuse trace 可上报（如本次环境启用）。
- [ ] 已定义本次发布关注的核心指标（如 P95、错误率、429、402、worker backlog）。
- [ ] 已定义告警阈值和响应人。
- [ ] worker/Celery 运行状态已验证。
- [ ] 至少完成一次日志排障演练。

---

## 七、数据与恢复

- [ ] 数据库迁移已在目标环境执行并记录结果。
- [ ] 备份方案明确（Postgres/Qdrant/审计导出）。
- [ ] 至少完成一次恢复演练或恢复脚本验证。
- [ ] 已明确 RTO / RPO（哪怕是初版）。

---

## 八、性能与容量

- [ ] 已完成至少一轮负载测试。
- [ ] 已记录基础容量结论（如 10/50/100 并发建议）。
- [ ] 已确认 API、worker、LLM、Redis、Qdrant 中的主要瓶颈点。
- [ ] 若本次是试点交付，已明确试点用户规模与限制条件。

---

## 九、交付材料

- [ ] 已准备管理员部署手册。
- [ ] 已准备运维手册。
- [ ] 已准备升级/回滚说明。
- [ ] 已准备已知问题列表。
- [ ] 已准备试点边界说明（支持范围 / 不支持范围）。
- [ ] 已准备联系人与故障升级路径。

---

## 十、最终发布判定

### A. 正式商用可交付
满足条件：
- [ ] 第二节所有 P0 阻断项全部完成
- [ ] 第三、四、五、六、七节无重大未决问题
- [ ] TL / QA / DevOps / Owner 共同签字通过

### B. 可内部试点 / 灰度
满足条件：
- [ ] 存在少量 P1/P2 缺口，但不影响受控范围试点
- [ ] 已明确告知试点限制条件
- [ ] 有回滚与应急预案

### C. 不可发布
任一情况触发即判定不可发布：
- [ ] P0 阻断项未完成
- [ ] CI 主链不稳定
- [ ] 生产默认安全配置仍存在
- [ ] 无法完成新环境部署或回滚演练
- [ ] 关键链路（登录/运行/查看详情）存在阻断性问题

---

## 发布记录

- 发布版本：`____________________`
- 发布环境：`____________________`
- 发布日期：`____________________`
- 发布负责人：`____________________`
- TL：`____________________`
- QA：`____________________`
- DevOps：`____________________`
- Owner：`____________________`
- 最终结论：
  - [ ] 正式商用可交付
  - [ ] 可内部试点 / 灰度
  - [ ] 不可发布
- 备注：

```text

```
