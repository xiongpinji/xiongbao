# R24 Candidate Freeze Execution Sheet

> 日期：2026-07-07
> Owner：Claude Code
> 范围：把 R23 的“最小可送审候选文件集”进一步收敛为**可执行冻结动作单**。
> 边界：本清单定义执行顺序与默认建议；**不等于已经冻结候选**，也不替代 branch / commit / CI 的实际执行结果。

---

## 1. 默认执行口径

若负责人没有额外指令，R24 默认按以下口径执行：

### 默认纳入
- `.github/workflows/ci.yml`
- `README.md`
- `apps/api` 下本轮真实源码与测试改动
- `apps/web/src`、`apps/web/tests`、`apps/web/public/assets` 下本轮真实源码/测试/静态资源改动
- `tests/e2e/specs/creative-smoke.spec.ts`
- `tests/e2e/specs/full-flow.spec.ts`
- `deploy/compose/.env.example`
- `deploy/compose/docker-compose.yml`
- `deploy/helm/templates/worker-web.yaml`
- 最小 release/readiness 文档主干：
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
  - `docs/ENVIRONMENT_BASELINE_V1.md`
  - `docs/RELEASE_RUNBOOK_V1.md`
  - `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md`
  - `docs/ROADMAP.md`
  - `docs/DEPLOYMENT_RUNBOOK.md`
  - `docs/INTEGRATION_GUIDE.md`
  - `docs/项目总览与开发指南.md`
  - `docs/XIONG_BAO_接手与启动说明_2026-07-03.md`
  - `docs/coordination/TASK_BOARD.md`
  - `docs/coordination/reports/delivery-report.md`
  - `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
  - `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
  - `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`
  - `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`
  - `docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`

### 默认排除
- `apps/api/*.log`
- `apps/web/*.log`
- `apps/api/r3-canvas-snapshot.json`
- `apps/web/08_diff_fix/codex-ui-1to1-audit-20260705.md`
- `docs/FRONTEND_*.md`
- `docs/superpowers/plans/*`
- `docs/coordination/EXECUTION_LIVE_OUTPUT_PROTOCOL.md`
- `docs/coordination/README.md`
- `docs/coordination/TASK_PACKAGE_PROTOCOL.md`

### 默认不进最小候选、需另行拍板
- `deploy/helm/templates/deployment.yaml`
- `deploy/helm/values.yaml`
- `deploy/keycloak/xagent-realm.json`
- `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
- `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`
- `docs/coordination/reports/evidence/r9-key-pages/*`
- `tests/e2e/specs/r9-visual-evidence.spec.ts`

---

## 2. 真正冻结前的准备动作

### Step 1：明确这次冻结的目标

本次冻结目标应统一为：

> **形成一个最小可送审候选，用于绑定新的 branch / commit / 远端 CI，并为后续 R4 / R5 提供稳定输入。**

在这一步，不能把目标说成：

- 正式发布完成
- R4 已完成
- R5 已可签发

---

## 3. 可执行冻结动作单

## Step 2：不要直接 `git add .`

冻结前的第一条纪律：

> **不要运行 `git add .` 或 `git add -A`。**

原因：
- 当前工作树有日志、snapshot、过程文档、一次性审计材料；
- 直接全量 add 会把不该进候选的文件一并带入。

---

## Step 3：先处理排除项

冻结前先把明显排除项从候选范围里剥离。这里的“剥离”是指：

- 不加入 staged set
- 不进入候选 commit
- 如有需要，可在单独分支/本地保留，但不计入本次候选

### 必排除清单

#### 日志
- `apps/api/api-8000.err.log`
- `apps/api/api-8000.log`
- `apps/api/r3-api-8000.err.log`
- `apps/api/r3-api-8000.log`
- `apps/web/frontend-3000-20260702-201604.err.log`
- `apps/web/frontend-3000-20260702-201604.log`
- `apps/web/frontend-3000-20260703-123118.err.log`
- `apps/web/frontend-3000-20260703-123118.log`
- `apps/web/r3-web-3100.err.log`
- `apps/web/r3-web-3100.log`

#### 运行态快照 / 一次性审计
- `apps/api/r3-canvas-snapshot.json`
- `apps/web/08_diff_fix/codex-ui-1to1-audit-20260705.md`

#### 过程性文档
- `docs/FRONTEND_*.md`
- `docs/superpowers/plans/*`
- `docs/coordination/EXECUTION_LIVE_OUTPUT_PROTOCOL.md`
- `docs/coordination/README.md`
- `docs/coordination/TASK_PACKAGE_PROTOCOL.md`

---

## Step 4：按“最小候选集合”分组暂存

建议按组进行，而不是一次性全加。

### 4.1 代码与测试组

优先暂存：

- `.github/workflows/ci.yml`
- `README.md`
- `apps/api/xagent/`
- `apps/api/tests/`
- `apps/web/src/`
- `apps/web/tests/`
- `apps/web/public/assets/`
- `tests/e2e/specs/creative-smoke.spec.ts`
- `tests/e2e/specs/full-flow.spec.ts`
- `deploy/compose/.env.example`
- `deploy/compose/docker-compose.yml`
- `deploy/helm/templates/worker-web.yaml`

### 4.2 文档主干组

再暂存：

- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`
- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md`
- `docs/ROADMAP.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/INTEGRATION_GUIDE.md`
- `docs/项目总览与开发指南.md`
- `docs/XIONG_BAO_接手与启动说明_2026-07-03.md`
- `docs/coordination/TASK_BOARD.md`
- `docs/coordination/reports/delivery-report.md`
- `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
- `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
- `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`
- `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`
- `docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`

---

## Step 5：列 staged 清单，逐项过一遍

暂存之后，必须检查：

1. staged 文件名列表
2. staged diff 统计
3. staged diff check

检查目标：
- 是否仍混入 `.log`、snapshot、一次性审计笔记
- 是否 accidentally 把拍板项一起带进来了
- 是否遗漏关键源码或关键 release 文档

---

## Step 6：拍板项单独决策

以下项目不要默认进入最小候选，必须单独给出 YES / NO：

| 项目 | 默认建议 | 若 YES 的影响 |
|---|---|---|
| `deploy/helm/templates/deployment.yaml` | NO | 扩大本次候选部署边界到 Helm 主模板 |
| `deploy/helm/values.yaml` | NO | 需要同时为 Helm 值文件承担审查责任 |
| `deploy/keycloak/xagent-realm.json` | NO | 需要把 identity/realm 配置一并纳入本轮候选 |
| `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md` | NO（最小候选外） | 把 R4 前置清单作为扩展审查输入包纳入 |
| `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md` | NO（最小候选外） | 把 R5 源数据矩阵纳入候选文档包 |
| `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md` | NO（最小候选外） | 把无密 handoff 模板纳入送审包 |
| `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md` + `evidence/` | NO（最小候选外） | 把视觉验收证据一起送审 |
| `tests/e2e/specs/r9-visual-evidence.spec.ts` | NO | 把视觉证据生成型 E2E 一起纳入 |

---

## Step 7：冻结 branch / commit

在 staged 范围确认、拍板项确认之后，才进入真正冻结动作：

1. 创建候选分支
2. 形成唯一候选 commit
3. 记录 branch / commit / 时间戳
4. push 到远端
5. 绑定远端 CI run

只有这一步完成后，才能说：

> **当前候选已冻结。**

---

## Step 8：冻结后再做的事

冻结完成后，不要立刻宣称可发布，下一步应是：

1. 用该候选 branch / commit 跑远端 CI
2. 用该候选作为 R4 输入
3. R4 证据归档后，再进入 R5
4. 关键 REVIEW 包验收完成后，再组装 reviewer 包

顺序不能跳过：

> **候选冻结 → 远端 CI → R4 → R5**

---

## 4. 一个最务实的默认拍板建议

如果你现在要最快进入真正冻结，我建议默认拍板如下：

- `ci.yml`：**YES，随候选冻结**
- Helm 主模板：**NO**
- Keycloak realm：**NO**
- R16 / R17 / R19 / R9：**NO，先不进最小候选，作为扩展审查包保留**

这样能最快形成一个：

> **最小可送审候选**

而不会因为部署边界和证据包过宽，拖慢冻结本身。

---

## 5. 一句话结论

> 真正的冻结动作，不是“把当前所有改动都提交”，而是：**先排除不该进入候选的东西，再按最小候选集合分组暂存，最后在拍板项确认后形成唯一 branch / commit / CI 绑定。**
