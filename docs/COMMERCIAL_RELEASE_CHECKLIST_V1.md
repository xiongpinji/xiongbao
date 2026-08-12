# X-Agent 商用发布前检查表 v1

> 用途：在对外试点、内部验收、预发布或正式发布前，由发布负责人逐项打勾。若任一 **P0 阻断项** 未完成，则本次发布不得标记为“正式商用可交付”。
>
> **2026-07-06 readiness 预检口径：** 本轮 P0-A 到 P0-E 已补齐本地收口证据和最小 CI 基线；本检查表复选框仍是具体版本 / 具体环境的发布签字项，未产生版本号、Git tag、远端 CI 全绿记录和环境演练记录前，不得勾选为正式商用可交付。
>
> **2026-08-12 说明：** 下列已勾选项记录的是 `v1.0.0` 与历史演练，不自动签发当前 R3 本地 `master`。R3 已通过本地独立验收，但当前提交仍需远端 push/CI、新版本 tag/Release 和目标环境签字，才能形成新的正式发布记录。

---

## 一、版本与范围确认

- [x] 本次发布有唯一版本号 / Git tag / 发布分支记录。（v1.0.0；tag `v1.0.0`；master 主线）
- [x] 本次发布范围已冻结，未提交工作树不属于交付内容。（发布点工作树干净）
- [x] 已明确本次交付包含哪些页面、接口、能力域。（`docs/RELEASE_NOTES_V1.0.0.md` §本版本能力总览）
- [x] 已明确本次不包含哪些实验性或后续能力。（Release Notes §本次发布不包含：短剧工厂行业交付/多机 HA/E2B/SaaS 级并发）
- [x] `README.md`、`docs/ROADMAP.md`、`docs/项目总览与开发指南.md`、`docs/XIONG_BAO_接手与启动说明_2026-07-03.md` 的项目状态口径一致。（R8 口径收口，2026-08-03 owner 验收）
- [x] 已存在唯一事实源文档：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`。

## 二、P0 阻断项（未完成不得正式发布）

### 2.1 文档与口径
- [x] README 中不再出现与真实状态冲突的阶段描述。（R8 终检）
- [x] ROADMAP 已区分“历史已完成”和“当前仍在硬化”的内容。（ROADMAP.md / ROADMAP_V2.md / ROADMAP_V3.md 分层）
- [x] 对外口径已由 TL/Owner 审核通过。（R5 §0.4/§0.5 owner 签发，2026-08-03/04）

### 2.2 前端首发范围
- [x] 首发页面范围已冻结并文档化。（R9 页面清单 + Release Notes 范围）
- [x] 当前发布所需前端资源已纳入版本控制。
- [x] 与发布无关的实验性页面/组件未混入正式发布包。（P0-C preview/demo 污染清理）
- [x] 关键页面（登录、对话、工作流、Run Console、设置）已有截图或验收记录。（R9 证据包）

> R9 本地页面验收证据见 `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`；复选框仍保留为具体版本 / 具体环境的发布负责人签字项。

### 2.3 runtime 失败闭环
- [x] direct run 失败时，运行详情可见失败原因。（R10 差异归因 + R13 full-flow 9/9）
- [x] stream run 失败时，运行详情可见失败原因。（R13 Chat SSE 闭环修复）
- [x] workflow/task 失败时，Run Console 可见状态、证据、建议动作。
- [x] 前端存在 blocked / failed / retryable 的明确展示，不是空白或静默失败。
- [x] 至少完成一次“失败→定位→恢复/重试”的人工演练。（P1 auto_recovery 四类动作实测，2026-08-04；证据 test_ops_automation.py 21 项）

### 2.4 安全默认值
- [x] 生产环境不允许使用默认 `admin/admin`。（P0-D：full 模式无默认账号，bootstrap 环境变量引导）
- [x] 生产环境不允许使用默认 JWT secret。（P0-D：生产 fail-fast + validate_helm_values CRITICAL 门禁）
- [x] `deploy/compose/docker-compose.yml` 中商用危险默认值已处理。（P0-D；v1.0.0 追加：数据面/内部服务全部改绑 127.0.0.1）
- [x] `deploy/helm/values.yaml` 中 `change-me` 类占位已改为显式必填策略。（P0-D + ESO 落地）
- [x] `XAGENT_CORS_ORIGINS` 未包含 `*`。（validate_for_production 硬校验 + CI config-governance 门禁）
- [x] 已确认 `require_auth` 没有被关闭。（CI config-governance REQUIRED_SAME_KEYS 机器校验）
- [x] Langfuse 默认账号密码已修改或禁用初始化默认用户。（P0-D）

### 2.5 发布与回滚
- [x] 已存在 `docs/RELEASE_RUNBOOK_V1.md`。
- [x] 已明确发布步骤、DB 迁移步骤、回滚步骤。
- [x] 已在新环境或 staging 环境完整演练过一次。（R31：当前机器 isolated compose `xagent-r4` 等价环境 full-mode 实跑 2026-08-03，owner 已接受作为本次交付依据；非本机目标环境仍属边界）
- [x] 演练过程中保留了日志、截图、结果记录。（delivery-report R31 段 + audit-20260802/）

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

- [x] backend `pytest -q` 通过。（670 通过 / 0 失败 / 10 跳过，PYTEST_EXIT=0）
- [x] backend `ruff check xagent tests` 通过。（口径说明：存量报告制 287 项基线、门禁为 0 新增——v1.0.0 全程改动均按此基线验证，逐轮 evidence 见 audit-20260802/ 各 pytest/ruff 记录）
- [x] frontend `npm run typecheck` 通过。（0 错误）
- [x] frontend `npm run build` 通过。（路由级拆包后无 chunk warning）
- [x] frontend `npm run lint` 通过。（0 错误，100 warnings 为存量报告制）
- [x] 至少一组关键 Playwright E2E 已纳入发布前门禁并通过。（CI e2e-api job + full-flow 9/9，R13）
- [x] 本次发布对应 CI 记录全部绿色。（master run 30979776573 起连续全绿，含 docker-build/load-test/promptfoo-eval）

---

## 三、功能与体验验收

### 3.1 基础链路
- [x] `/health` 返回正常。（安全扫描实跑 2026-08-05 + CI e2e-api）
- [x] `/ready` 返回正常。（同上，database/cache 组件全 healthy）
- [x] 登录链路可用。（full-flow E2E + 多实例 JWT 实测 2026-08-04）
- [x] 登录后工作台首页无阻断报错。（R9 验收记录）
- [x] Run Console 可打开并展示运行详情。（R9/R13）

### 3.2 核心能力
- [x] 智能体运行链路可完成一次成功执行。（full-flow E2E + 真实 LLM 冷烟 2026-08-05）
- [x] 工作流创建/查看/审批链路可完成一次验证。（full-flow 9/9）
- [x] 记忆/检索链路可完成一次验证。（test 覆盖 + R3）
- [x] 开源发现链路可完成一次验证。（CAPABILITY_VERIFICATION_20260803）
- [x] 短剧工厂/画布链路可完成一次验证（若属于本次交付范围）。（**本次不包含**：短剧工厂行业交付已暂停，非 v1.0.0 验收链路）
- [x] 设置页与关键系统配置展示无明显断链。（R9 设置页截图与验收）

### 3.3 用户体验
- [x] 空状态、失败态、加载态没有明显空白页或无说明崩溃。（R9 验收 + P0-C）
- [x] 错误提示可被用户理解，不是纯技术堆栈信息。
- [x] 导航结构与首发版定义一致。（R9）
- [x] 多语言/文案不会出现大面积未翻译或占位文本。（P0-C 演示态标识清理）

---

## 四、环境与配置基线

> 环境基线与 secret 注入说明见 `docs/ENVIRONMENT_BASELINE_V1.md`；以下复选框仍需按具体环境实测后由发布负责人勾选。

- [x] 已区分 dev / staging / prod 配置。（helm 四环境模板 + CONFIG_GOVERNANCE_V1 差异策略门禁）
- [x] 关键 secret 来源清晰（env / secret manager / k8s secret）。（ENVIRONMENT_BASELINE_V1 + ESO/secretRef）
- [x] 所有外部依赖地址与凭据已按环境配置。
- [x] 生产环境已明确使用哪种 LLM 路径（OpenAI / DeepSeek / Ollama / LiteLLM）。（compose 默认 Ollama，可切 LiteLLM Proxy；文档明确定义）
- [x] 若启用 OIDC/Keycloak，JWKS 与 issuer 配置已验证。（SANDBOX_SSO_VERIFICATION_20260803）
- [x] 若启用 OpenFGA/ContextForge，其健康状态已检查。（R31 full-mode 等价环境实跑）
- [x] 对象存储（如启用）已验证 put/get/delete。（test_users_storage 对象存储双测试）

---

## 五、安全与合规

- [x] `python scripts/license_check.py` 通过。（CI license-gate job 全绿）
- [x] 安全扫描通过：`python tests/security/scan.py --host http://localhost:8000`。（2026-08-05 实跑 PASS；限流项 lite 低阈值不触发为扫描器自述边界）
- [x] 跨租户访问防护已验证。（scan 跨租户头注入 403 + 测试覆盖）
- [x] 鉴权/权限不足场景返回符合预期。（401/403 测试矩阵）
- [x] 安全响应头存在。（scan 验证 X-Content-Type-Options / X-Frame-Options）
- [x] 限流可触发并返回 429。（HA_MULTI_INSTANCE_VERIFY_20260803 实测 429；P2 复测）
- [x] 审计导出可执行。（test_enterprise audit export + PostgresAuditLog）
- [x] 已确认数据库、Redis、Qdrant 不直接公网裸露。（v1.0.0 修复：compose 数据面/内部服务全部改绑 127.0.0.1；对外仅 web:3000 / api:8000 / grafana:3002）
- [x] HTTPS / TLS 终止方案已明确。（DEPLOYMENT_RUNBOOK：Nginx 终止 TLS）

---

## 六、可观测与运维

- [x] `/metrics` 可访问。
- [x] Grafana 仪表板已导入或有等价监控视图。（deploy/grafana 仪表板 + prometheus alert-rules）
- [x] Langfuse trace 可上报（如本次环境启用）。（verify_langfuse + SANDBOX_SSO_REVERIFY_20260803）
- [x] 已定义本次发布关注的核心指标（如 P95、错误率、429、402、worker backlog）。（slo.yml + helm alerting rules）
- [x] 已定义告警阈值和响应人。（阈值：alerting rules / Alertmanager 联动；响应人初版：发布负责人 canqu）
- [x] worker/Celery 运行状态已验证。（compose worker healthcheck 修正 + full-mode 实跑 R31）
- [x] 至少完成一次日志排障演练。（OPERATIONS_MANUAL 排障路径 + P1 恢复链实测演练记录）

---

## 七、数据与恢复

- [x] 数据库迁移已在目标环境执行并记录结果。（R31 alembic current + P2 Postgres 全量迁移实测 2026-08-04）
- [x] 备份方案明确（Postgres/Qdrant/审计导出）。（scripts/backup.py）
- [x] 至少完成一次恢复演练或恢复脚本验证。（scripts/restore.py + RECOVERY_PACK_TEMPLATE 演练纪律）
- [x] 已明确 RTO / RPO（哪怕是初版）。（OPERATIONS_MANUAL_V1 §8 初版：RTO ≤30min / RPO ≤6h，多机热备除外）

---

## 八、性能与容量

- [x] 已完成至少一轮负载测试。（LOAD_TEST_FORMAL_20260803：10min soak + Postgres + 多 worker 两轮）
- [x] 已记录基础容量结论（如 10/50/100 并发建议）。（同文档 §2/§3）
- [x] 已确认 API、worker、LLM、Redis、Qdrant 中的主要瓶颈点。（三瓶颈治理实测闭环）
- [x] 若本次是试点交付，已明确试点用户规模与限制条件。（PILOT_PACK_TEMPLATE 进入条件与边界）

---

## 九、交付材料

> 当前材料索引见 `docs/DELIVERY_MATERIALS_INDEX_V1.md`。其中管理员部署手册、运维手册、升级/回滚说明、已知问题/试点边界说明、支持与故障升级路径已形成最小交付包；正式商用签发前仍需按具体环境补齐真实联系人、R4 目标环境演练与最终签字。

- [x] 已准备管理员部署手册。（ADMIN_DEPLOYMENT_MANUAL_V1）
- [x] 已准备运维手册。（OPERATIONS_MANUAL_V1，含 RTO/RPO 初版）
- [x] 已准备升级/回滚说明。（RELEASE_RUNBOOK_V1 + UPGRADE_PACK_TEMPLATE）
- [x] 已准备已知问题列表。（KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1）
- [x] 已准备试点边界说明（支持范围 / 不支持范围）。（同上 §2）
- [x] 已准备联系人与故障升级路径。（SUPPORT_ESCALATION_PATH_V1；联系人初版=发布负责人 canqu，客户环境部署时回填实际联系人）

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

- 发布版本：`commercialization-ladder / 1cb4a28`
- 发布环境：`当前定义下的商用交付标准（Goal 收口完成）`
- 发布日期：`2026-07-20`
- 发布负责人：`canqu`
- TL：`canqu`
- QA：`canqu`
- DevOps：`canqu`
- Owner：`canqu`
- 最终结论：
  - [x] 正式商用可交付
  - [ ] 可内部试点 / 灰度
  - [ ] 不可发布
- 备注：

```text
- 当前商用交付标准按 G0/G1/G2/G3 Goal 体系收口判断。
- G1（内部试点可稳定使用）已完成。
- G2（正式商用 GA）已完成。
- G3（企业级长期运营）已完成治理骨架与四个执行包的首轮真实验证。
- G0 xagent 商用完整交付 已满足关闭条件。
```

---

## 发布记录（v1.0.0）

- 发布版本：`v1.0.0`（tag，发布落点见 master）
- 发布环境：`Compose full / Helm 四环境 / GHCR 镜像（api:1.0.0 / web:1.0.0）`
- 发布日期：`2026-08-05`
- 发布负责人：`canqu`
- TL：`canqu`
- QA：`canqu`
- DevOps：`canqu`
- Owner：`canqu`
- 证据总入口：`docs/RELEASE_NOTES_V1.0.0.md`（质量证据节）+ `audit-20260802/`（各轮 pytest/压测/实测/签发记录）+ R5 包 §0.4/§0.5（owner 签发与延伸）
- 最终结论：
  - [x] 正式商用可交付（第四节边界维持：多机 HA / E2B / 非本机目标环境演练 / 短剧行业变体不外推）
  - [ ] 可内部试点 / 灰度
  - [ ] 不可发布
- 备注：

```text
- 本版本为 PR #7（269 提交）合入 master 后的首个正式 tag 版本。
- Roadmap v2（P0/P1/P2/P4 全闭环）与 v3（竞品差距补齐四轨）全部落地并实测。
- ruff 口径为存量报告制基线（287 项、0 新增门禁），已在 §2.6 显式声明。
- 安全扫描 2026-08-05 实跑 PASS；compose 数据面服务于本版本改绑 127.0.0.1。
```
