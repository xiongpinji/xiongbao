# X-Agent Roadmap v2 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 `ROADMAP_V2.md` 中的五个增强方向拆成可执行的下一轮工作路线，明确优先顺序、验证方法与交付物。

**架构：** 本计划不再讨论“是否达到商用交付标准”，而是在当前交付标准已达成的前提下，按平台化增强 → 自动化运营增强 → 容量与性能增强 → 商业复制增强 → 产品增强的顺序推进。每个方向都先冻结目标、再确认验证口径、最后形成可复制材料或实现结果。

**技术栈：** Markdown、GitHub Actions、FastAPI、React/Vite、Docker Compose、Helm、pytest、Playwright、Locust、Prometheus/Grafana、Langfuse、Postgres、Redis、Qdrant、K8s

---

## 文件结构与职责边界

### 新增文件

- `docs/superpowers/plans/2026-07-20-roadmap-v2-execution-plan.md`
  - Roadmap v2 的总执行计划、优先顺序与阶段门。
- `docs/coordination/reports/roadmap-v2-platformization-package.md`
  - 平台化增强方向的执行包说明。
- `docs/coordination/reports/roadmap-v2-ops-automation-package.md`
  - 自动化运营增强方向的执行包说明。
- `docs/coordination/reports/roadmap-v2-capacity-package.md`
  - 容量与性能增强方向的执行包说明。
- `docs/coordination/reports/roadmap-v2-delivery-replication-package.md`
  - 商业复制增强方向的执行包说明。
- `docs/coordination/reports/roadmap-v2-product-enhancement-package.md`
  - 产品增强方向的执行包说明。

### 修改文件

- `docs/ROADMAP_V2.md`
  - 若后续需要，把已执行项 / 已冻结项回填进文档。
- `docs/coordination/reports/commercialization-goal-board.md`
  - 在 G0 关闭后新增 Roadmap v2 入口，作为下一轮增强路线入口。
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`
  - 追加 Roadmap v2 执行包入口，便于后续统一检索。

---

### 任务 1：建立 Roadmap v2 总执行板

**文件：**
- 创建：`docs/superpowers/plans/2026-07-20-roadmap-v2-execution-plan.md`
- 修改：`docs/coordination/reports/commercialization-goal-board.md`

- [ ] **步骤 1：写出 Roadmap v2 总执行骨架**

```md
# Roadmap v2 Execution Board

## A 平台化增强
- status: ready

## B 自动化运营增强
- status: pending

## C 容量与性能增强
- status: pending

## D 商业复制增强
- status: pending

## E 产品增强
- status: pending
```

- [ ] **步骤 2：运行文档校验**

运行：
`git diff --check -- docs/superpowers/plans/2026-07-20-roadmap-v2-execution-plan.md docs/coordination/reports/commercialization-goal-board.md`

预期：退出码 0。

- [ ] **步骤 3：将 Roadmap v2 入口挂回 Goal Board**

```md
## Next Track
- 当前主线已完成：G0 xagent 商用完整交付
- 当前进入：Roadmap v2
- 当前 active 方向：A 平台化增强
```

- [ ] **步骤 4：Commit**

```bash
git add docs/superpowers/plans/2026-07-20-roadmap-v2-execution-plan.md docs/coordination/reports/commercialization-goal-board.md
git commit -m "docs(roadmap): add roadmap v2 execution board"
```

---

### 任务 2：冻结 A 平台化增强包

**文件：**
- 创建：`docs/coordination/reports/roadmap-v2-platformization-package.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 引用：`deploy/helm/values.yaml`
- 引用：`docs/ENVIRONMENT_BASELINE_V1.md`

- [ ] **步骤 1：写出平台化增强包模板**

```md
# Roadmap v2 A 平台化增强包

## 目标
- secretRef / external secret manager
- Helm/K8s 平台化补齐
- 标准环境模板
- 平台级配置治理
```

- [ ] **步骤 2：补入验证方向与输出物**

```md
## 输出物
- 平台化路线
- K8s/Helm 增强入口
- secret 注入目标形态
- 环境模板定义
```

- [ ] **步骤 3：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/roadmap-v2-platformization-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md`

预期：退出码 0。

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/roadmap-v2-platformization-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md
git commit -m "docs(roadmap): define platformization package"
```

---

### 任务 3：冻结 B 自动化运营增强包

**文件：**
- 创建：`docs/coordination/reports/roadmap-v2-ops-automation-package.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 引用：`docs/OPERATIONS_MANUAL_V1.md`
- 引用：`docs/RELEASE_RUNBOOK_V1.md`

- [ ] **步骤 1：写出自动化运营增强包模板**

```md
# Roadmap v2 B 自动化运营增强包

## 目标
- 自动告警联动
- 自动恢复
- 自动证据归档
- 自动运行态汇总
```

- [ ] **步骤 2：补入最小验证方向**

```md
## 验证方向
- 哪些动作仍依赖人工
- 哪些环节适合自动化
- 自动化后预期减少什么人工成本
```

- [ ] **步骤 3：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/roadmap-v2-ops-automation-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md`

预期：退出码 0。

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/roadmap-v2-ops-automation-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md
git commit -m "docs(roadmap): define ops automation package"
```

---

### 任务 4：冻结 C 容量与性能增强包

**文件：**
- 创建：`docs/coordination/reports/roadmap-v2-capacity-package.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 引用：`docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- 引用：`docs/coordination/reports/commercialization-g3-c4-capacity-verification.md`

- [ ] **步骤 1：写出容量增强包模板**

```md
# Roadmap v2 C 容量与性能增强包

## 目标
- 正式压测基线
- 多实例一致性实证
- 队列 / 缓存 / LLM 路径瓶颈治理
- 容量建议与限制策略
```

- [ ] **步骤 2：补入验证出口**

```md
## 输出物
- 压测结论
- 瓶颈清单
- 扩容建议
- 用户规模建议
```

- [ ] **步骤 3：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/roadmap-v2-capacity-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md`

预期：退出码 0。

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/roadmap-v2-capacity-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md
git commit -m "docs(roadmap): define capacity package"
```

---

### 任务 5：冻结 D 商业复制增强包

**文件：**
- 创建：`docs/coordination/reports/roadmap-v2-delivery-replication-package.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 引用：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 引用：`docs/ADMIN_DEPLOYMENT_MANUAL_V1.md`
- 引用：`docs/OPERATIONS_MANUAL_V1.md`

- [ ] **步骤 1：写出商业复制增强包模板**

```md
# Roadmap v2 D 商业复制增强包

## 目标
- 标准交付模板
- 标准试点包 / 升级包 / 恢复包
- 角色模板
- 不同行业场景交付变体
```

- [ ] **步骤 2：补入可复制输出物**

```md
## 输出物
- 标准模板列表
- 角色模板清单
- 场景化变体列表
```

- [ ] **步骤 3：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/roadmap-v2-delivery-replication-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md`

预期：退出码 0。

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/roadmap-v2-delivery-replication-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md
git commit -m "docs(roadmap): define delivery replication package"
```

---

### 任务 6：冻结 E 产品增强包

**文件：**
- 创建：`docs/coordination/reports/roadmap-v2-product-enhancement-package.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 引用：`docs/coordination/reports/commercialization-goal-board.md`

- [ ] **步骤 1：写出产品增强包模板**

```md
# Roadmap v2 E 产品增强包

## 目标
- Goal / taskboard 自动推进增强
- review / recover / evidence 自动化增强
- 更强工作台体验
- 更细粒度执行与治理视图
```

- [ ] **步骤 2：补入增强输出物**

```md
## 输出物
- 增强方向清单
- 优先级说明
- 不破坏现有交付基线的约束
```

- [ ] **步骤 3：运行文档校验**

运行：
`git diff --check -- docs/coordination/reports/roadmap-v2-product-enhancement-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md`

预期：退出码 0。

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/roadmap-v2-product-enhancement-package.md docs/DELIVERY_MATERIALS_INDEX_V1.md
git commit -m "docs(roadmap): define product enhancement package"
```

---

## 自检

### 规格覆盖度
- 平台化增强（A）有独立任务。
- 自动化运营增强（B）有独立任务。
- 容量与性能增强（C）有独立任务。
- 商业复制增强（D）有独立任务。
- 产品增强（E）有独立任务。
- 所有方向都从“目标 → 输出物 → 校验 → 提交”拆分为可执行步骤。

### 占位符扫描
- 无 TODO / TBD / 待定。
- 无“类似任务”类复用占位。
- 每个任务都包含具体文件路径和具体命令。

### 类型一致性
- 方向名称统一为 A/B/C/D/E。
- 所有增强方向都归于 `ROADMAP_V2.md`。
- 所有包文档统一放在 `docs/coordination/reports/`。

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-07-20-roadmap-v2-execution-plan.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选哪种方式？