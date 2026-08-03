# X-Agent 当前真实状态（唯一事实源）

> **用途：** 本文档是 `xagent` 当前项目状态、发布口径与商用 readiness 判断的唯一事实源。凡是 README、ROADMAP、项目总览、接手说明、对外同步材料与本文件冲突时，以本文件为准。
>
> **更新时间：** 2026-08-03（增补：Roadmap v2 P0 平台化与 P2 容量实证落地证据、CI 门禁补强；README 口径同步修正）
>
> **适用对象：** owner、研发、QA、交付、下一位接手者。

---

## 1. 状态口径定义

为避免“已经实现”与“已经可以正式商用”混淆，项目统一使用以下四类状态：

### 1.1 已实现（Implemented）
代码、路由、页面、适配器或流程已经落在仓库中，具备基本结构与运行路径。

### 1.2 已验证（Verified）
不仅已实现，而且已有本地实跑、测试、日志、构建、脚本或文档证据支持。

### 1.3 仍在硬化（Hardening）
主链可用，但在一致性、失败态、交互细节、默认配置、安全基线、发布治理或运维能力上仍在持续收口。

### 1.4 接入点预留（Integration-ready）
接口、抽象、降级逻辑或配置位已存在，但真实商用级接入、长期运营或规模化验证尚未完全完成。

---

# 2. 当前一句话判断

`xagent` 当前处于：

> **G1（内部试点）/ G2（正式商用 GA）/ G3（企业级长期运营治理与首轮验证）已全部完成，项目已达到当前定义下的商用交付标准，可按"正式商用可交付"口径对外表述。当前进入 Roadmap v2 增强阶段，重点投向平台化、自动化运营、容量实证与商业复制能力。**

## 2.1 商用成熟度阶段映射

- G1（内部试点可稳定使用）：**已完成**
- G2（正式商用 GA）：**已完成**
- G3（企业级长期运营治理与首轮验证）：**已完成**
- 当前阶段：**Roadmap v2 增强期**（平台化 / 自动化运营 / 容量实证 / 商业复制 / 产品增强）

## 2.2 当前推进规则

- G1 / G2 / G3 均已关闭，不再回退到"是否达标"的旧问题
- 后续新增工作统一按 Roadmap v2 方向归类（增强项 / 规模化项 / 平台化项 / 复制能力项）
- 新增强项不得回退已有 G0/G1/G2/G3 的完成结论

这意味着：

- 它**不是从 0 到 1 的原型**。
- 它**也不是没有后续演进空间的终态产品**。
- 它更准确地属于：**已完成商用交付标准、正在向平台化与规模化持续演进的成熟产品**。

### 2.1 商用成熟度阶段映射（历史口径存档）

> 以下为 2026-07-06 时的阶段口径，已被上方最新结论取代，仅作历史参考。

- 当时激活阶段：G1（内部试点可稳定使用）
- G2：当时未开启（后已完成）
- G3：当时未开启（后已完成）

### 2.2 当前推进规则（历史口径存档）

> 以下为 2026-07-06 时的推进规则，已被上方最新结论取代，仅作历史参考。

- 当时仅 G1 处于 active
- G2 Gate：功能链路、稳定性 / 恢复、数据 / 权限 / 审计、试点交付材料（后已全部通过）
- G3 Gate：候选冻结、目标环境演练、发布 / 回滚、签字 / 证据（后已全部通过）

---

## 3. 当前真实状态拆解

### 3.1 产品与技术面
以下判断成立：

- 多数核心能力域已经实现，且文档中对 Phase 0~5 的功能版图描述总体有代码落点支撑。
- lite / dev 路径当前可以作为理解项目、验证页面、排查问题的推荐入口。
- full / compose 路径具备私有部署基础，但其含义更接近“可部署、可验证主链”，不等于“运维与交付体系已经完全收口”。

### 3.2 前端面
以下判断成立：

- 前端工作台仍在重构与体验收口中。
- 当前仓库存在较多前端未提交改动，说明发布范围尚未彻底冻结。
- 短剧工厂自由画布、Run Console、设置页索引库等方向已经明确，但仍应视为**活跃迭代区域**。

### 3.3 runtime / 交付面
以下判断成立：

- unified runtime 主链已经形成，但失败态一致性、详情精确度、前端失败闭环仍是近期重点。
- 近期实现计划仍围绕 runtime Phase2-A 加固展开，这说明“主链可用”不等于“失败闭环已经商用级收口”。
- 现阶段更适合内部试点、私有部署、受控交付，而不是对外承诺“完全封板”。

---

## 4. 当前已核验事实

截至 2026-07-06，本仓库可确认的事实包括：

- 后端健康检查可访问：`http://127.0.0.1:8000/health`
- 前端 dev server 可访问：`http://127.0.0.1:3000`
- 登录接口可用：`POST /api/v1/auth/login`
- lite / dev 本地验证路径仍可使用默认账号 `admin / admin`；full / enterprise 不再 seed 默认管理员，需显式提供凭据
- 当前推荐接手路径仍是 **lite / dev 优先**，而不是一上来就走 compose/full
- orchestration prompt-tool fallback 缺少 `await` 的 correctness bug 已修复，并有最小回归测试覆盖
- 前端 `npm run lint`、`npm run typecheck` 与 `npm run build` 已通过；CI 已补入对应前端静态 / 构建门禁
- 前端依赖风险已形成 R11 审计记录：`npm audit --omit=dev` 为 0；全量 `npm audit` 仍有 Vite / esbuild dev-build 工具链 1 moderate / 1 high，需发布负责人显式接受或另拆依赖升级包
- 前端 Vite chunk size warning 已通过 R14 路由级懒加载拆包清除：`npm run build` 通过且未再出现 warning，最大 JS chunk 为 294.19 kB / gzip 96.09 kB；这不替代真实性能压测或目标环境演练
- 商用危险默认值已做 fail-fast 或显式配置处理，发布环境仍必须提供真实 secret
- CI 后端最小门禁保留 `ruff check xagent tests` 与 `pytest -q`
- 发布 / 回滚 Runbook v1 已补充为 `docs/RELEASE_RUNBOOK_V1.md`；目标环境完整演练与证据归档仍需后续 R4 完成
- dev / staging / prod 环境基线与 secret 注入说明已补充为 `docs/ENVIRONMENT_BASELINE_V1.md`；真实目标环境 secret manager / secretRef 接入仍需 R4 或平台化任务演练
- 交付材料索引与最小交付包已补充为 `docs/DELIVERY_MATERIALS_INDEX_V1.md`、`docs/ADMIN_DEPLOYMENT_MANUAL_V1.md`、`docs/OPERATIONS_MANUAL_V1.md`、`docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`、`docs/SUPPORT_ESCALATION_PATH_V1.md`；其中真实联系人、目标环境演练结果与最终签字仍需按具体交付环境补齐
- full-mode 演练前置清单已形成 R16 证据：已整理 R4 恢复所需的 Langfuse secrets、JWT secret、显式账号、端口、依赖服务、LLM 路径和 compose config 预检；该清单不替代 R4 目标环境实跑
- README、ROADMAP、项目总览与接手说明已按本唯一事实源补齐当前发布口径，差异清单见 `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md`
- 关键页面本地截图 / 验收记录已补充为 `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`；真实目标环境页面验收仍需 R4 或发布负责人签字
- R4 full-mode 演练已在当前机器形成一轮等价环境实跑证据：isolated compose 项目 `xagent-r4` 已拉起，`/health` 与 `/ready` 返回 200，`alembic current` 为 `0005 (head)`，`python -m xagent.cli smoke` 通过，`tests/e2e/specs/full-flow.spec.ts --project=chromium` 已 9/9 通过；该证据仍属于当前机器上的单机等价环境，不自动等同于客户目标环境签字
- SQLite/Alembic 漂移已形成 R12 诊断：当前迁移 head 为 `0005`，fresh SQLite 可迁移并包含 `evidence_records`；旧本地 `apps/api/xagent.db` 为未知 revision `0007` 且缺 `evidence_records`，不得作为当前发布证据
- Chat SSE 完成态已形成 R13 修复与证据：`readAgentRunStream` 对无 `done` 的流结束显式失败并触发 fallback，Chat 主区在 done-only run 下显示“查看运行详情”；本地 `full-flow.spec.ts` 已 9/9 通过，目标环境复验仍需 R4
- Vite chunk warning 已形成 R14 修复与证据：`App.tsx` 改为路由级 `React.lazy` / `Suspense` 拆包，本地 `full-flow.spec.ts` 仍 9/9 通过；该证据不等于正式性能或发布签字

这些事实来自接手说明、对应运行日志与本轮协调交付证据，而不是纯规划口径。

### 4.1 2026-08-03 增补事实（Roadmap v2 落地证据）

- **P0 平台化已落地并实测**：`secretRef` 外部密管（`SECRETREF:file:/env:`，生产 fail-fast，vault 预留）+ Helm chart 产品化（全套模板 + default/dev/staging/prod/enterprise 五套 values 渲染通过）— 944675b；P0 不再停留于方向层
- **SSO/OIDC 授权码流端到端实测通过**：Keycloak 26 discovery/302/换票/JWKS 验签/JIT 开户/state 防重放；SSO token 与本地账号 token 双源共存（alg 路由双源校验，伪造双算法均拒）— `audit-20260802/SANDBOX_SSO_REVERIFY_20260803.md`
- **沙箱分级 L1 Docker 实测通过**：stdout/stderr 分流回收、只读 rootfs/禁网/内存限额/超时 kill/一次性容器、逃逸尝试全拦截；python_exec 在沙箱 disabled 时 fail-closed 不回退宿主机；L2 E2B 代码就绪（无 key 未实测）— 同上
- **P2 容量实证第一轮闭环**：三瓶颈（bcrypt 同步阻塞 / skills 双重序列化 / 限流硬编码）全部修复并实测——login c=50 3.2→54.8 RPS（17×）、skills c=50 31.5→162.3 RPS（5.2×）、限流 XAGENT_SECURITY__RATE_LIMIT_* 全项可配
- **P2 正式压测**：10min soak 142,720 请求全 200 无泄漏迹象；Postgres 目标配置不劣于 SQLite；4 worker 形态 canvas c=10 达 606 RPS（6.4×）— `audit-20260802/LOAD_TEST_FORMAL_20260803.md`
- **CI 门禁补强**：PR #7 新候选 backend/frontend/license-gate/e2e-api 全绿（run 30829673045）；e2e-api 与 backend 解耦防止连带 SKIPPED 掩盖 API 漂移；/perf 端点存量 bug 修复
- **多实例共享状态（限流/登录锁定/调度锁）已同机两实例实测**（HA_MULTI_INSTANCE_VERIFY_20260803）；多机 HA/Redis 自身高可用仍未演练；**L2 E2B 未实测**（无 key）；**非当前机器的目标环境演练仍未做**——此三项维持原边界不外推

---

## 5. 历史阶段完成 ≠ 当前正式 GA

项目中存在两类容易混淆的信息：

1. **历史里程碑口径**
   - 如“Phase 0~5 已完成”“若干能力域已实现并通过当时验收”。
2. **当前发布口径**
   - 即“今天这个仓库是否已经完成版本冻结、前端收口、runtime 闭环、安全默认值清零、发布回滚与标准运维准备”。

统一解释如下：

- **历史阶段完成** 表示功能与骨架建设曾经达成既定验收目标。
- **当前正式 GA** 需要额外满足文档一致性、首发范围冻结、失败态闭环、安全基线、CI 门禁、发布回滚演练等商用条件。
- 因此，不能再把“历史阶段完成”直接等同于“当前已经完全商用收口”。

---

## 6. 当前建议的对外口径

### 6.1 可以这样说

- `xagent` 已具备较完整的功能版图与私有部署基础。
- 项目主链可运行，适合内部试点、受控交付和产品化推进。
- 当前仍在进行商用 readiness 收口，重点包括前端版本冻结、runtime 失败闭环、环境安全基线与发布治理。

### 6.2 不建议这样说

- “项目已经完全封板，当前仓库就是最终商用版。”
- “所有文档中的已完成都等于今天可以无条件正式对外商用。”
- “当前没有前端或 runtime 硬化工作在进行。”

---

# 7. 当前优先级（2026-07-26 起，Roadmap v2 阶段）

G1/G2/G3 已完成，当前优先级按 Roadmap v2 方向排列：

### P0（平台化增强）
- ✅ `secretRef` / external secret manager 已落地（file:/env:，生产 fail-fast；vault 预留）— 2026-08-03
- ✅ Helm chart 产品化补齐（五套 values 渲染通过）— 2026-08-03
- ✅ 标准环境模板（dev / staging / prod / enterprise values）— 2026-08-03
- 平台级配置治理与差异控制（进行中）

### P1（自动化运营增强）
- 自动告警联动
- 自动恢复与自动归档
- run / workflow 证据链自动生成
- 发布后观测结果自动汇总

### P2（容量与性能实证）
- ✅ 正式压测基线（两轮：基线 + soak/Postgres/多 worker）— 2026-08-03
- 多实例一致性与扩容实证（Redis 化完成，多实例实测未做）
- ✅ 队列 / 缓存 / LLM 路径瓶颈治理（三瓶颈修复实测；skills/login 路径）— 2026-08-03

### P3（商业复制增强）
- 标准交付模板与角色包
- 标准试点包 / 升级包 / 恢复包
- 行业 / 场景交付变体包

### P4（产品增强）
- Goal / taskboard 自动推进能力
- review / recover / evidence 自动化
- 工作台体验与治理视图深化

---

## 8. 与其他文档的关系

- `README.md`
  - 用于建立总体心智模型与快速启动。
  - 不再单独承担“项目真实状态唯一事实源”的职责。
- `docs/ROADMAP.md`
  - 用于区分历史阶段、当前收口重点与后续商用增强方向。
- `docs/项目总览与开发指南.md`
  - 作为功能版图、技术架构、历史里程碑的权威入口。
  - 当前发布状态判断仍以本文件为准。
- `docs/XIONG_BAO_接手与启动说明_2026-07-03.md`
  - 用于帮助接手者快速启动与理解当前仓库现实。
  - 若与本文件冲突，优先以本文件为准。

---

## 9. 维护约定

以下情况发生时，必须同步更新本文件：

- 发布口径发生变化
- 首发范围冻结或解冻
- runtime 硬化从“进行中”转为“已收口”
- 默认安全配置清零完成
- 发布 / 回滚演练通过
- 项目从“试点可交付”升级为“正式商用可交付”

---

## 10. 当前结论（供快速引用）

**当前结论：**

G1/G2/G3 已全部完成，项目按当前定义达到商用交付标准，处于 Roadmap v2 增强期。截至 2026-08-03：P0 平台化（secretRef + Helm）与 P2 容量实证（三瓶颈修复 + soak/Postgres/多 worker 基线）已落地并实测；新候选（c175201 后 221 提交，PR #7 HEAD 2aae3a2）已获 owner 重新签发（见 R5 包 §0.4）。剩余边界为——多机 HA 未演练（共享状态类已同机两实例实测）、L2 E2B 云沙箱未实测（无 key）、非当前机器的目标环境演练未做。

> `xagent` 已达到当前定义下的**商用交付标准**。项目已完成内部试点可稳定使用（G1）、正式商用 GA（G2）与企业级长期运营治理与首轮验证（G3）的完整 Goal 收口，当前可以明确按“正式商用可交付”口径对外表述。后续若继续推进，将属于下一轮增强与演进，而不是当前交付标准仍未达成。