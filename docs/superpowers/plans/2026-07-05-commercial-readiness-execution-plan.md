# X-Agent 商用 Readiness 收口计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把当前 `xagent` 从“主链已可运行、前端和 runtime 仍在持续硬化”的准商用状态，推进到“可冻结版本、可标准发布、可对外试点交付”的商用 readiness 基线。

**架构：** 本计划不新增产品大功能，优先收口事实源文档、前端发布版本、runtime 失败闭环、安全默认值、发布回滚与质量门禁。执行顺序遵循 P0 → P1 → P2，其中 P0 是发布阻断项，P1 是标准交付项，P2 是规模化演进项。交付物以文档、配置门禁、CI 校验、验证记录和可复现发布流程为主。

**技术栈：** Markdown、GitHub Actions、FastAPI、React/Vite、Docker Compose、Helm、pytest、Playwright、Locust、Langfuse、Prometheus/Grafana

---

## 文件结构与职责边界

### 核心新增文件

- `docs/superpowers/plans/2026-07-05-commercial-readiness-execution-plan.md`
  - 商用 readiness 甘特式执行表、阶段目标、角色分工、依赖关系。
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
  - 商用发布前打勾式检查表，供发布负责人逐项核验。
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - 项目唯一真实状态文档：已完成、进行中、接入点预留、已验证范围。
- `docs/RELEASE_RUNBOOK_V1.md`
  - 发布、回滚、Smoke 验证、迁移与故障兜底流程。
- `docs/ENVIRONMENT_BASELINE_V1.md`
  - dev/staging/prod 配置基线、secret 约束、默认值禁用策略。
- `docs/OPERATIONS_SLO_V1.md`
  - SLO/SLA、告警阈值、值班响应策略。

### 核心修改文件

- `README.md`
  - 更新项目阶段状态、发布口径、指向真实状态文档。
- `docs/ROADMAP.md`
  - 把历史阶段状态与当前收口任务对齐，避免与总览矛盾。
- `docs/项目总览与开发指南.md`
  - 将“已完成”与“当前仍在硬化”的边界重写为一致口径。
- `docs/XIONG_BAO_接手与启动说明_2026-07-03.md`
  - 关联真实状态文档，避免后续再分叉。
- `.github/workflows/ci.yml`
  - 把前端 build/typecheck/lint、关键 E2E、发布 smoke 纳入门禁；收紧 mypy 策略。
- `deploy/compose/docker-compose.yml`
  - 去除商用环境危险默认值；增加启动前失败校验说明与变量约束。
- `deploy/helm/values.yaml`
  - 去除 `change-me` 风险默认值，改为显式必填占位或 secretRef 模式说明。
- `apps/web/src/components/runs/RunConsole.tsx`
  - 仅在 runtime 闭环仍缺失时补失败态 UX 收口。
- `apps/web/src/api/client.ts`
  - 若需要补统一错误码/重试/跳转策略，在 P0-3 中收口。

### 角色定义（用于甘特表）

- **TL（Tech Lead）**：技术负责人，拍板口径、推进依赖、验收阻断项。
- **BE（Backend）**：后端/运行时负责人。
- **FE（Frontend）**：前端工作台负责人。
- **DevOps**：发布、CI、容器、监控、环境配置负责人。
- **QA**：验收、E2E、安全扫描、发布 smoke 负责人。
- **Sec**：安全基线、secret、权限与默认配置审阅负责人。
- **PM/Owner**：对外口径、试点范围、版本承诺负责人。

---

## 甘特式执行表（按 P0 / P1 / P2）

> 约定：`W1`=第 1 周，`W2`=第 2 周，依此类推。若团队只有 2~3 人，可把 FE/BE/DevOps 角色由同一人兼任，但顺序依赖不变。

### P0（发布阻断项，预计 2 周）

| ID | 任务 | 负责人 | 配合 | 前置依赖 | 预计工期 | 周期 | 交付物 | 说明 |
|---|---|---|---|---|---:|---|---|---|
| P0-1 | 统一真实状态文档 | TL | PM/Owner | 无 | 1 天 | W1 D1 | `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` | 定义“已完成/进行中/预留接入点” |
| P0-2 | 同步 README/ROADMAP/总览/接手说明口径 | TL | FE/BE | P0-1 | 1.5 天 | W1 D1-D2 | 4 份文档修订 | 消除阶段状态冲突 |
| P0-3 | 冻结前端发布范围与页面清单 | FE | TL/QA | P0-1 | 1 天 | W1 D2 | 页面验收矩阵、截图基线 | 决定哪些未提交改动进入首发版 |
| P0-4 | 收口 Run Console / runtime 失败闭环清单 | BE | FE/QA | P0-3 | 2 天 | W1 D3-D4 | 缺口列表、修复列表 | 仅做闭环，不扩功能面 |
| P0-5 | 消除商用危险默认值（JWT/admin/change-me） | Sec | DevOps/BE | P0-1 | 1 天 | W1 D4 | 环境基线修订 | 生产环境默认值必须 fail fast |
| P0-6 | 增加发布/回滚 runbook v1 | DevOps | TL/BE | P0-5 | 1.5 天 | W1 D4-D5 | `docs/RELEASE_RUNBOOK_V1.md` | 包含 DB 迁移、镜像发布、回滚 |
| P0-7 | 收紧 CI 最小门禁 | DevOps | FE/BE/QA | P0-3,P0-4 | 2 天 | W2 D1-D2 | 更新 `ci.yml` | 至少包含前端 typecheck/build、关键 E2E、smoke |
| P0-8 | 试点发布演练（空环境部署→登录→核心链路） | QA | DevOps/BE/FE | P0-6,P0-7 | 2 天 | W2 D3-D4 | 演练记录、问题单 | 必须在新环境重复成功 |
| P0-9 | P0 Go/No-Go 评审 | TL | 全员 | P0-8 | 0.5 天 | W2 D5 | 发布判定纪要 | 未过项不可对外承诺正式商用 |

#### P0 时间轴（文本甘特）

```text
W1:  P0-1 █  P0-2 ██  P0-3 █  P0-4 ██  P0-5 █  P0-6 ██
W2:  P0-7 ██ P0-8 ██ P0-9 ▌
```

#### P0 完成定义

- [ ] 文档口径统一，README/ROADMAP/总览/接手说明不再互相矛盾。
- [ ] 前端存在明确“首发版范围”，不再以未收口工作树作为交付基线。
- [ ] runtime 失败态可见、可解释、可恢复。
- [ ] 生产环境无法带默认 secret / 默认账户 / 开放配置启动。
- [ ] 发布与回滚流程可在新环境复现一遍。
- [ ] CI 已能阻断明显的前后端回归。

---

### P1（标准商用交付项，预计 3~4 周）

| ID | 任务 | 负责人 | 配合 | 前置依赖 | 预计工期 | 周期 | 交付物 | 说明 |
|---|---|---|---|---|---:|---|---|---|
| P1-1 | 环境基线文档化（dev/staging/prod） | DevOps | Sec/BE | P0-5 | 2 天 | W3 D1-D2 | `docs/ENVIRONMENT_BASELINE_V1.md` | 明确变量、依赖、secret 来源 |
| P1-2 | 角色/权限/登录模式商用说明 | Sec | BE/PM | P0-1 | 2 天 | W3 D2-D3 | 权限矩阵文档 | 内置账号 / SSO 的支持边界 |
| P1-3 | SLO/告警/监控基线 | DevOps | TL/QA | P0-8 | 2 天 | W3 D3-D4 | `docs/OPERATIONS_SLO_V1.md` | P95、成功率、429/402、worker backlog |
| P1-4 | 备份恢复演练 | DevOps | QA/BE | P1-1 | 2 天 | W3 D4-D5 | 恢复记录 | Postgres/Qdrant/审计导出验证 |
| P1-5 | 性能基线压测 | QA | BE/DevOps | P0-8 | 2 天 | W4 D1-D2 | Locust 基线报告 | 给出 10/50/100 并发建议 |
| P1-6 | 客户交付文档包 | PM/Owner | TL/QA | P1-1,P1-2,P1-3 | 3 天 | W4 D2-D4 | 管理员/运维/升级手册 | 形成标准试点交付包 |
| P1-7 | staging 回归发布一次 | QA | 全员 | P1-4,P1-5,P1-6 | 2 天 | W4 D4-D5 | staging release 记录 | 以真实流程走一遍 |

#### P1 时间轴（文本甘特）

```text
W3:  P1-1 ██ P1-2 ██ P1-3 ██ P1-4 ██
W4:  P1-5 ██ P1-6 ███ P1-7 ██
```

#### P1 完成定义

- [ ] 不同环境的配置基线与 secret 管理方式明确。
- [ ] 权限模型与登录模式边界可对客户解释。
- [ ] 有 SLO/告警，不只停留在 dashboard 存在。
- [ ] 备份恢复经过实操验证。
- [ ] 压测基线形成可供售前/交付引用的数据。
- [ ] 已可交付一套标准试点文档包。

---

### P2（规模化/企业化增强项，预计 4~8 周，可并行）

| ID | 任务 | 负责人 | 配合 | 前置依赖 | 预计工期 | 周期 | 交付物 | 说明 |
|---|---|---|---|---|---:|---|---|---|
| P2-1 | HA/K8s 多实例验证 | DevOps | BE | P1-7 | 1 周 | W5 | 多实例验收记录 | 包含 API/worker 横向扩容 |
| P2-2 | 分布式一致性/幂等/重试策略收口 | BE | DevOps | P2-1 | 1 周 | W6 | 设计说明 + 验证结果 | 尤其针对 task/workflow/runtime |
| P2-3 | 审计/隔离/保留策略合规化 | Sec | BE/PM | P1-2 | 1 周 | W6 | 审计与保留策略文档 | 面向企业采购/法务 |
| P2-4 | 版本策略与兼容承诺 | PM/Owner | TL | P1-6 | 3 天 | W7 | 版本策略说明 | 稳定版、快速版、API 兼容口径 |
| P2-5 | 插件/provider 兼容矩阵与熔断策略 | TL | BE/QA | P1-7 | 1 周 | W7-W8 | 兼容矩阵、故障隔离策略 | 为后续规模化接入做准备 |

#### P2 时间轴（文本甘特）

```text
W5:  P2-1 █████
W6:  P2-2 █████  P2-3 █████
W7:  P2-4 ███    P2-5 █████
W8:  P2-5 █████
```

#### P2 完成定义

- [ ] 至少有一套多实例部署验证结果。
- [ ] 任务/工作流的分布式一致性边界清楚。
- [ ] 审计与租户隔离满足更正式的企业审查。
- [ ] 对外有明确版本与兼容承诺。
- [ ] 外部 provider / 插件出现异常时不会拖垮主链。

---

## 执行顺序与关键依赖

### 必须先做的顺序

1. **P0-1 → P0-2**：先统一事实源，再谈计划和发布。
2. **P0-3 → P0-4**：先冻结前端范围，再做 runtime 闭环收口。
3. **P0-5 → P0-6**：先明确安全基线，再形成发布/回滚流程。
4. **P0-7 → P0-8**：先把门禁接进 CI，再做真实演练。
5. **P1-1/P1-2/P1-3**：环境、权限、监控是标准交付三件套。
6. **P1-4/P1-5/P1-6 → P1-7**：恢复、压测、文档包准备好后再跑 staging 发布。

### 可以并行的部分

- P1-1 与 P1-2 可并行。
- P1-3 与 P1-4 可部分并行，但 SLO 指标定义应先于告警和恢复演练结论。
- P2-2 与 P2-3 可并行。
- P2-4 可与 P2-5 并行。

---

## 风险与应对

### 风险 1：文档对齐引发“已完成”口径缩水争议
- **触发条件：** README/ROADMAP 改写后，团队认为对外叙述变弱。
- **应对：** 在 `COMMERCIAL_STATUS_SOURCE_OF_TRUTH` 中把“已实现”“已验证”“仍在硬化”拆开，避免非黑即白。

### 风险 2：前端冻结范围迟迟定不下来
- **触发条件：** 工作树持续变化，新增页面与重构交错。
- **应对：** 由 TL/Owner 在 P0-3 明确首发范围；超出范围的改动推迟到 P1 或单独里程碑。

### 风险 3：runtime 闭环工作膨胀成大重构
- **触发条件：** 修失败态时顺带改模型、事件流、页面结构。
- **应对：** P0-4 只修“失败可见/可解释/可恢复”；不得顺便扩新能力。

### 风险 4：CI 门禁一收紧就大面积失败
- **触发条件：** 前端或 E2E 基线不稳。
- **应对：** 先引入关键 smoke 套件，再逐步扩大；但首发前必须有阻断链路。

---

## 里程碑验收命令（建议）

### P0 验收

```bash
# backend
cd apps/api
pytest -q
ruff check xagent tests

# frontend
cd ../web
npm run typecheck
npm run build
npm run lint

# e2e / smoke
cd ../../tests/e2e
npm test
```

预期：
- backend 通过
- frontend build/typecheck/lint 通过
- 至少 1 组关键 E2E 通过
- runbook 中的新环境演练步骤可以复现

### P1 验收

```bash
# load
cd apps/api
locust -f tests/load/locustfile.py --host http://localhost:8000 --headless -u 50 -r 5 -t 60s

# security
python tests/security/scan.py --host http://localhost:8000
```

预期：
- 形成负载基线报告
- 安全扫描通过
- 备份恢复演练记录可审阅

### P2 验收

```bash
# staging / multi-instance / release drill
# 由 DevOps 按 RELEASE_RUNBOOK_V1 执行；要求保留日志、截图、指标与回滚记录
```

预期：
- 多实例验证通过
- 回滚可执行
- 企业审计/隔离材料可复用

---

## 任务分解（最小执行粒度）

### 任务 1：统一项目真实状态文档

**文件：**
- 创建：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 修改：`README.md`
- 修改：`docs/ROADMAP.md`
- 修改：`docs/项目总览与开发指南.md`
- 修改：`docs/XIONG_BAO_接手与启动说明_2026-07-03.md`

- [ ] **步骤 1：编写真实状态文档初稿**
- [ ] **步骤 2：把“已实现 / 已验证 / 进行中 / 接入点预留”四种状态定义写清楚**
- [ ] **步骤 3：逐个修订 README / ROADMAP / 总览 / 接手说明中的冲突表述**
- [ ] **步骤 4：让 TL/Owner 评审发布口径**
- [ ] **步骤 5：提交一次文档收口 commit**

### 任务 2：冻结前端首发范围

**文件：**
- 修改：`apps/web/src/**`
- 创建：`docs/FRONTEND_RELEASE_SCOPE_V1.md`

- [ ] **步骤 1：列出当前未提交前端改动清单**
- [ ] **步骤 2：按“首发必须 / 可延后 / 实验性”分类**
- [ ] **步骤 3：补首发页面截图清单**
- [ ] **步骤 4：冻结首发版的导航和核心页面范围**
- [ ] **步骤 5：提交一次前端范围冻结 commit**

### 任务 3：收口 runtime 失败闭环

**文件：**
- 修改：`apps/api/xagent/**`
- 修改：`apps/web/src/components/runs/**`
- 测试：`apps/api/tests/**`
- 测试：`apps/web/tests/**`

- [ ] **步骤 1：列出 direct/stream/task/workflow 失败态差异**
- [ ] **步骤 2：先补失败用例，再修后端状态和 evidence**
- [ ] **步骤 3：前端补 blocked/failed/retryable 展示与动作**
- [ ] **步骤 4：跑后端测试、前端测试和最小人工验收**
- [ ] **步骤 5：提交一次 runtime 收口 commit**

### 任务 4：商用安全默认值清零

**文件：**
- 修改：`deploy/compose/docker-compose.yml`
- 修改：`deploy/helm/values.yaml`
- 创建：`docs/ENVIRONMENT_BASELINE_V1.md`

- [ ] **步骤 1：列出所有默认弱配置与默认账户**
- [ ] **步骤 2：把生产危险默认值改为显式必填或 fail fast**
- [ ] **步骤 3：补环境基线文档和 secret 来源说明**
- [ ] **步骤 4：验证在缺少关键 secret 时启动失败**
- [ ] **步骤 5：提交一次安全基线收口 commit**

### 任务 5：发布/回滚与 CI 门禁收口

**文件：**
- 创建：`docs/RELEASE_RUNBOOK_V1.md`
- 修改：`.github/workflows/ci.yml`
- 创建：`docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`

- [ ] **步骤 1：编写发布/回滚 runbook**
- [ ] **步骤 2：把前端门禁、关键 E2E、smoke 纳入 CI**
- [ ] **步骤 3：生成发布前检查表并让 QA 试用一遍**
- [ ] **步骤 4：在 staging 或新环境做一次完整演练**
- [ ] **步骤 5：提交一次发布治理收口 commit**

---

## 自检结果

### 规格覆盖度
- 已覆盖：P0/P1/P2 执行顺序、负责人、工期、依赖、验收、风险、交付物。
- 已覆盖：发布前检查表的产出位置。
- 已覆盖：文档对齐、前端范围冻结、runtime 闭环、安全默认值、CI 门禁、发布演练。

### 占位符扫描
- 未使用 “TODO / 后续实现 / 待定” 作为任务内容。
- 未使用“类似任务 N”替代具体动作。
- 所有阶段都给出了明确交付物与完成定义。

### 类型一致性
- P0/P1/P2 的角色命名、文件路径、交付物名称在全文保持一致。

---

计划已完成并保存到 `docs/superpowers/plans/2026-07-05-commercial-readiness-execution-plan.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
