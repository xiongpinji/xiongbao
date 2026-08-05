# R28 Candidate Freeze Pre-Execution Checklist

> 日期：2026-07-07
> Owner：Claude Code
> 范围：把已决范围（R27）转换为真正冻结前可逐条执行的检查单。
> 边界：本清单用于执行前核对与顺序控制；**不自动执行 git add / branch / commit / push**。

---

## 1. 适用前提

使用本清单前，默认以下条件已经成立：

- 已接受 `R27_DECIDED_FREEZE_SCOPE_MEMO.md` 中的默认拍板结果；
- 本轮采用 **最小可送审候选**；
- `ci.yml` 随候选冻结；
- Helm / Keycloak / R16 / R17 / R19 / R9 视觉证据 / `r9-visual-evidence.spec.ts` **不进入本轮最小候选**。

如果上述任一项变化，应先回退到 R26 / R27，重新确认范围，再继续执行。

---

## 2. 执行目标

本清单的目标不是“发布”，而是完成以下更小一步：

> **形成一个干净、可检查、可绑定 branch / commit / CI 的 staged candidate。**

完成本清单后，应达到：

- 候选范围固定到 staged set；
- staged set 不包含排除项；
- staged set 与 R25 精确暂存清单一致；
- 可以安全进入 branch / commit / push / CI 绑定动作。

---

## 3. 执行前禁止事项

在执行本清单期间，禁止：

- 直接运行 `git add .`
- 直接运行 `git add -A`
- 在未核对 staged set 前创建候选 commit
- 把日志、snapshot、过程文档、扩展证据包混入最小候选
- 把 staged candidate 误称为“已冻结候选”

---

## 4. 执行检查单

## Step 0：确认当前目标

- [ ] 当前目标是“形成 staged candidate”，不是“完成发布”
- [ ] 当前目标不是 R4 演练完成
- [ ] 当前目标不是 R5 已可签发
- [ ] 已接受最小可送审候选模式

---

## Step 1：确认排除项不进入候选

必须确认以下内容**不进入本轮 staged set**：

### 日志
- [ ] `apps/api/api-8000.err.log`
- [ ] `apps/api/api-8000.log`
- [ ] `apps/api/r3-api-8000.err.log`
- [ ] `apps/api/r3-api-8000.log`
- [ ] `apps/web/frontend-3000-20260702-201604.err.log`
- [ ] `apps/web/frontend-3000-20260702-201604.log`
- [ ] `apps/web/frontend-3000-20260703-123118.err.log`
- [ ] `apps/web/frontend-3000-20260703-123118.log`
- [ ] `apps/web/r3-web-3100.err.log`
- [ ] `apps/web/r3-web-3100.log`

### snapshot / 一次性材料
- [ ] `apps/api/r3-canvas-snapshot.json`
- [ ] `apps/web/08_diff_fix/codex-ui-1to1-audit-20260705.md`

### 过程性文档
- [ ] `docs/FRONTEND_*`
- [ ] `docs/superpowers/plans/*`
- [ ] `docs/coordination/EXECUTION_LIVE_OUTPUT_PROTOCOL.md`
- [ ] `docs/coordination/README.md`
- [ ] `docs/coordination/TASK_PACKAGE_PROTOCOL.md`

如果以上任一文件已经被加入 staged set，应先移出 staged，再继续。

---

## Step 2：暂存 A 组（代码 / 测试 / 运行配置）

按 R25 的 A 组执行暂存，并逐组核对：

### 2.1 根目录与 CI
- [ ] `.github/workflows/ci.yml`
- [ ] `README.md`

### 2.2 后端源码与测试
- [ ] `apps/api/xagent/...`
- [ ] `apps/api/tests/...`

### 2.3 前端源码 / 测试 / 静态资源
- [ ] `apps/web/src/...`
- [ ] `apps/web/tests/...`
- [ ] `apps/web/public/assets/...`

### 2.4 E2E
- [ ] `tests/e2e/specs/creative-smoke.spec.ts`
- [ ] `tests/e2e/specs/full-flow.spec.ts`

### 2.5 运行配置
- [ ] `deploy/compose/.env.example`
- [ ] `deploy/compose/docker-compose.yml`
- [ ] `deploy/helm/templates/worker-web.yaml`

---

## Step 3：暂存 B 组（最小文档主干）

按 R25 的 B 组执行暂存，并逐项核对：

### 3.1 核心状态 / 门禁 / 手册
- [ ] `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- [ ] `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- [ ] `docs/ENVIRONMENT_BASELINE_V1.md`
- [ ] `docs/RELEASE_RUNBOOK_V1.md`
- [ ] `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md`
- [ ] `docs/ROADMAP.md`
- [ ] `docs/DEPLOYMENT_RUNBOOK.md`
- [ ] `docs/INTEGRATION_GUIDE.md`
- [ ] `docs/项目总览与开发指南.md`
- [ ] `docs/XIONG_BAO_接手与启动说明_2026-07-03.md`

### 3.2 当前候选 / 交付主索引
- [ ] `docs/coordination/TASK_BOARD.md`
- [ ] `docs/coordination/reports/delivery-report.md`
- [ ] `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
- [ ] `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
- [ ] `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`
- [ ] `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`
- [ ] `docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`
- [ ] `docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`
- [ ] `docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`
- [ ] `docs/coordination/reports/R26_YES_NO_DECISION_SHEET_FOR_CANDIDATE_FREEZE.md`
- [ ] `docs/coordination/reports/R27_DECIDED_FREEZE_SCOPE_MEMO.md`

---

## Step 4：确认拍板项没有误入 staged set

本轮默认**不应**出现在 staged set 中：

- [ ] `deploy/helm/templates/deployment.yaml`
- [ ] `deploy/helm/values.yaml`
- [ ] `deploy/keycloak/xagent-realm.json`
- [ ] `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
- [ ] `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- [ ] `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- [ ] `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`
- [ ] `docs/coordination/reports/evidence/r9-key-pages/*`
- [ ] `tests/e2e/specs/r9-visual-evidence.spec.ts`

如果这些文件中有任意一个出现在 staged set，需要先判断：
- 是误加？则移出 staged
- 是负责人新拍板改为 YES？则回写 R27 / R26 口径后再继续

---

## Step 5：检查 staged set

在形成 commit 前，必须检查以下四项：

### 5.1 staged 文件列表
- [ ] staged list 与 R25 的 A / B 组一致
- [ ] staged list 不包含排除项
- [ ] staged list 不包含未拍板项

### 5.2 staged diff 统计
- [ ] diff 规模与当前候选预期一致
- [ ] 未出现“明显不属于本轮候选”的陌生路径

### 5.3 staged diff check
- [ ] `git diff --check --cached` 无阻断问题

### 5.4 验证口径仍成立
- [ ] 前端 `lint/typecheck/build` 通过
- [ ] 后端 `ruff/pytest` 通过
- [ ] Python 许可证门禁通过

---

## Step 6：通过后才能进入真正冻结动作

只有在 Step 1 到 Step 5 全部完成后，才进入：

1. 创建候选分支
2. 形成唯一候选 commit
3. 记录 branch / commit / 时间戳
4. push 到远端
5. 获取新的远端 CI run

到这一步之后，才可以说：

> **候选已冻结。**

在这之前，都只能说：

> **候选范围已决 / staged candidate 已就绪**

---

## 5. 一句话结论

> R28 的作用是把“真正冻结前要逐条确认什么”变成一张执行检查单；只有这张清单过完，R25 才能从“建议暂存列表”进入“可安全提交的 staged candidate”。
