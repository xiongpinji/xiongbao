# X-Agent 商用完整交付 Goal 结构落地计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在现有 `xagent` 仓库中正式建立 `G0/G1/G2/G3` 商用完整交付 Goal 结构，并只展开当前阶段 `G1`，优先落地 `G1-A1`（功能链路包）与 `G1-A2`（稳定性 / 恢复包）的执行入口。

**架构：** 采用“文档冻结 + 目标入口 + 执行包”三层落地方式。项目级 `G0` 与阶段级 `G1/G2/G3` 先用文档与协调任务板固化，避免在目标未明确前直接扩展产品代码；当前阶段只展开 `G1`，并通过可执行的功能/恢复包文档、验证脚本和证据入口驱动实现，待 `G1` 通过 Gate 后再进入 `G2`。

**技术栈：** Markdown、Git、FastAPI Spine API、React Goal Board、GitHub Actions、pytest、Playwright、Docker Compose

---

## 文件结构与职责边界

### 新增文件

- `docs/coordination/reports/commercialization-goal-board.md`
  - 冻结 `G0/G1/G2/G3`、执行包状态、当前 active 包、blocked 字段模板；这是项目级 Goal 板的唯一文本视图。
- `docs/coordination/reports/commercialization-g1-a1-functional-package.md`
  - `G1-A1` 功能链路包：固定内部试点标准日常路径、入口、验证命令、证据位置。
- `docs/coordination/reports/commercialization-g1-a2-stability-package.md`
  - `G1-A2` 稳定性 / 恢复包：失败场景、恢复演练脚本、证据要求、可回查入口。

### 修改文件

- `docs/coordination/TASK_BOARD.md`
  - 增加 Goal 结构入口，标出当前激活阶段为 `G1`，并把 `G1-A1/G1-A2` 设为首批执行包。
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - 补充“当前商用成熟度阶段 = G1”的明确口径，以及 G0 只在三阶段完成后关闭的规则。
- `docs/ROADMAP.md`
  - 将 `Phase 1 / 2 / 3` 商用成熟度门与现有历史 Phase 0-5 进行映射，避免命名混淆。
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`
  - 补 Goal 板与 `G1-A1/G1-A2` 的入口，让试点负责人知道从哪里看当前阶段与执行包。
- `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
  - 补“当前仅激活 G1，G2/G3 未开启”的边界说明。
- `README.md`
  - 增加指向 Goal 板与商用推进文档的最小入口，不修改主口径定义。

### 可能引用但不修改的文件

- `docs/superpowers/specs/2026-07-19-xagent-commercialization-goal-structure-design.md`
- `docs/coordination/reports/commercial-readiness-phase1-gap-analysis.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`
- `apps/api/xagent/api/v1/spine.py`
- `apps/web/src/pages/GoalBoardPage.tsx`

---

### 任务 1：建立项目级 Goal 板文档

**文件：**
- 创建：`docs/coordination/reports/commercialization-goal-board.md`
- 修改：`docs/coordination/TASK_BOARD.md`

- [ ] **步骤 1：编写失败的 Goal 板骨架文档**

```md
# X-Agent Commercialization Goal Board

## G0 xagent 商用完整交付
- status: active
- close condition: G1 + G2 + G3 全部 done

## G1 内部试点可稳定使用
- status: active
- active package: G1-A1
- ready packages: G1-A2

## G2 正式商用 GA
- status: pending

## G3 企业级长期运营
- status: pending
```

- [ ] **步骤 2：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/commercialization-goal-board.md docs/coordination/TASK_BOARD.md`

预期：退出码 0。

- [ ] **步骤 3：将 Goal 入口挂回任务板**

```md
## Goal Board Entry
- 当前总 Goal：`G0 xagent 商用完整交付`
- 当前激活阶段：`G1 内部试点可稳定使用`
- 当前 active 包：`G1-A1 功能链路包`
- 当前 ready 包：`G1-A2 稳定性 / 恢复包`
```

- [ ] **步骤 4：再次运行校验**

运行：
`git diff --check -- docs/coordination/reports/commercialization-goal-board.md docs/coordination/TASK_BOARD.md`

预期：退出码 0。

- [ ] **步骤 5：Commit**

```bash
git add docs/coordination/reports/commercialization-goal-board.md docs/coordination/TASK_BOARD.md
git commit -m "docs(goal): add commercialization goal board"
```

---

### 任务 2：把当前项目状态映射到 G1 / G2 / G3

**文件：**
- 修改：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 修改：`docs/ROADMAP.md`
- 修改：`docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`

- [ ] **步骤 1：编写失败的阶段映射草稿**

```md
## 商用成熟度阶段映射
- 当前激活阶段：G1 内部试点可稳定使用
- G2 未开启：尚缺版本冻结、目标环境演练、签字闭环
- G3 未开启：尚缺 HA / K8s / SLO / 审计保留 / 容量边界
```

- [ ] **步骤 2：运行文档校验**

运行：
`git diff --check -- docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/ROADMAP.md docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`

预期：退出码 0。

- [ ] **步骤 3：补入当前阶段规则**

```md
### 当前推进规则
- 仅 G1 处于 active
- G2 只有在 G1 四个 Gate 全部通过后开启
- G3 只有在 G2 四个 Gate 全部通过后开启
```

- [ ] **步骤 4：再次运行校验**

运行：
`git diff --check -- docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/ROADMAP.md docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`

预期：退出码 0。

- [ ] **步骤 5：Commit**

```bash
git add docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/ROADMAP.md docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md
git commit -m "docs(goal): map repo status to commercialization phases"
```

---

### 任务 3：展开 G1-A1 功能链路包

**文件：**
- 创建：`docs/coordination/reports/commercialization-g1-a1-functional-package.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 引用：`apps/web/src/pages/GoalBoardPage.tsx`
- 引用：`apps/web/src/App.tsx`
- 引用：`docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`

- [ ] **步骤 1：编写失败的功能包模板**

```md
# G1-A1 功能链路包

## 目标路径
1. 登录
2. 工作台入口
3. Goal Board / 任务入口
4. task / workflow / run 提交
5. 结果查看 / 回放

## 验收命令
- curl /health
- curl /ready
- npm --prefix apps/web test -- goalBoard.test.tsx
```

- [ ] **步骤 2：补入固定入口与证据位置**

```md
## 入口
- `/chat`
- `/goal-board`
- `/runs/:runId`
- `/settings`

## 现有证据
- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
```

- [ ] **步骤 3：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/commercialization-g1-a1-functional-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md`

预期：退出码 0。

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/commercialization-g1-a1-functional-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md
git commit -m "docs(goal): define g1-a1 functional package"
```

---

### 任务 4：展开 G1-A2 稳定性 / 恢复包

**文件：**
- 创建：`docs/coordination/reports/commercialization-g1-a2-stability-package.md`
- 修改：`docs/RELEASE_RUNBOOK_V1.md`
- 修改：`docs/ENVIRONMENT_BASELINE_V1.md`
- 引用：`docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
- 引用：`docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`

- [ ] **步骤 1：编写失败的稳定性包模板**

```md
# G1-A2 稳定性 / 恢复包

## 故障类型
- 任务失败
- 工作流失败
- 运行详情缺失
- 迁移失败
- 依赖不可用

## 恢复动作
- 重试
- 回看 evidence
- 回放 run
- 恢复依赖
```

- [ ] **步骤 2：补入最小演练脚本**

```md
## 演练脚本
1. 触发一个可控失败
2. 在 Goal Board / Run Console 中观察失败态
3. 根据 runbook 执行恢复
4. 记录日志、截图与结果
```

- [ ] **步骤 3：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/commercialization-g1-a2-stability-package.md docs/RELEASE_RUNBOOK_V1.md docs/ENVIRONMENT_BASELINE_V1.md`

预期：退出码 0。

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/commercialization-g1-a2-stability-package.md docs/RELEASE_RUNBOOK_V1.md docs/ENVIRONMENT_BASELINE_V1.md
git commit -m "docs(goal): define g1-a2 stability package"
```

---

### 任务 5：把 Goal 板与执行包入口挂回 owner / 接手者材料

**文件：**
- 修改：`README.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 修改：`docs/coordination/reports/auto-delivery-phase1-report.md`

- [ ] **步骤 1：编写失败的 owner 入口草稿**

```md
## Goal 入口
- 当前总 Goal：G0 xagent 商用完整交付
- 当前阶段：G1 内部试点可稳定使用
- 当前 active 包：G1-A1
- 当前 ready 包：G1-A2
```

- [ ] **步骤 2：运行文档校验**

运行：
`git diff --check -- README.md docs/DELIVERY_MATERIALS_INDEX_V1.md docs/coordination/reports/auto-delivery-phase1-report.md`

预期：退出码 0。

- [ ] **步骤 3：Commit**

```bash
git add README.md docs/DELIVERY_MATERIALS_INDEX_V1.md docs/coordination/reports/auto-delivery-phase1-report.md
git commit -m "docs(goal): link owner entrypoints to g0-g1"
```

---

## 自检

### 规格覆盖度
- Goal 结构中的 G0/G1/G2/G3 已由任务 1、2 建立与映射。
- 执行包层中的 G1-A1、G1-A2 已由任务 3、4 展开。
- “只激活 G1，不展开 G2/G3”的策略已体现在任务范围中。
- owner / 接手者入口已由任务 5 覆盖。

### 占位符扫描
- 无 TODO / TBD / 待定。
- 每个任务都给出了精确文件路径。
- 每个任务都包含明确校验命令与提交点。

### 类型一致性
- Goal 命名统一使用 `G0/G1/G2/G3`。
- 执行包命名统一使用 `G1-A1/G1-A2/...`。
- 文档入口统一放在 `docs/coordination/reports/` 与现有交付材料体系中。

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-07-19-xagent-commercialization-goal-structure-execution-plan.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选哪种方式？