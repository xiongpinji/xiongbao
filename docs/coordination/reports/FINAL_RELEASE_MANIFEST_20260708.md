# FINAL_RELEASE_MANIFEST_20260708

> 用途：把当前 `candidate/min-send-review-20260707-claude` 最新 HEAD `0eb864496f33e661566370536cec0d2624a023de` 的正式交付范围固定成一份最终清单，供归档、复盘、再交付和 reviewer 对照使用。
>
> 边界：本 manifest 只描述“本次正式交付纳入/排除什么”，不替代 `COMMERCIAL_RELEASE_CHECKLIST_V1.md`、`RELEASE_RUNBOOK_V1.md` 或最终签字记录块。

---

## 1. 对应候选

- 分支：`candidate/min-send-review-20260707-claude`
- 最终 HEAD：`0eb864496f33e661566370536cec0d2624a023de`
- 关键前一收口提交：`db29505fbce3f6bfe056d6e9073d82e6130e8988`
- PR：[#7](https://github.com/xiongpinji/xiongbao/pull/7)
- 最新远端 CI：`28921412457`（success）

---

## 2. 本次正式交付纳入范围

### 2.1 代码 / 配置

- `deploy/compose/docker-compose.yml`
- `tests/e2e/specs/full-flow.spec.ts`
- `.gitattributes`

说明：

- `docker-compose.yml` 纳入了 worker healthcheck 伪失败修复；
- `full-flow.spec.ts` 纳入了 replay/resume 选择器收口；
- `.gitattributes` 固定 shell 脚本 LF 行尾，避免 Windows → Linux 挂载时再次触发 `/bin/bash^M` 风险。

### 2.2 交付主文档

- `README.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- `docs/DEPLOYMENT_RUNBOOK.md`

### 2.3 交付材料包

- `docs/ADMIN_DEPLOYMENT_MANUAL_V1.md`
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`
- `docs/FORMAL_RELEASE_EXTERNAL_CONDITIONS_V1.md`
- `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
- `docs/OPERATIONS_MANUAL_V1.md`
- `docs/SUPPORT_ESCALATION_PATH_V1.md`

### 2.4 协调 / 审查 / 留档文档

- `docs/coordination/TASK_BOARD.md`
- `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
- `docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md`
- `docs/coordination/reports/delivery-report.md`

这些文件共同承担：

- R4 current-machine full-mode 等价环境实跑记录
- R5 最终审查包
- 最终签字输入块
- task board 状态收口
- 最终 wrap-up 审查入口

---

## 3. 本次明确排除范围

以下内容当前**不属于本次正式交付文件集**：

### 3.1 前端差异/过程材料

- `apps/web/08_diff_fix/**`
- `docs/FRONTEND_*.md`

### 3.2 协调协议类过程文档

- `docs/coordination/README.md`
- `docs/coordination/TASK_PACKAGE_PROTOCOL.md`
- `docs/coordination/EXECUTION_LIVE_OUTPUT_PROTOCOL.md`

### 3.3 历史审计 / 中间证据包

- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`
- `docs/coordination/reports/R10_FULL_FLOW_E2E_TRIAGE.md`
- `docs/coordination/reports/R11_NPM_AUDIT_FRONTEND_BUILD_RISK.md`
- `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
- `docs/coordination/reports/R14_VITE_CHUNK_SPLIT.md`
- `docs/coordination/reports/R15_EVIDENCE_SYNC.md`
- `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
- `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- `docs/coordination/reports/evidence/**`

说明：

- 这些文件仍可作为**背景证据或追溯材料**存在；
- 但当前正式交付候选没有把它们作为“必须随候选一并交付的文件集”。

### 3.4 计划 / superpowers 过程文件

- `docs/superpowers/plans/**`

---

## 4. 与 R4/R5 的关系

### 4.1 R4 证据不完全在候选文件内

当前机器上的 R4 等价环境实跑证据，除了仓库内文档记录外，还包含本地证据目录：

- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\compose-ps.txt`
- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\alembic-current.txt`
- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\api-smoke.txt`
- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\full-flow-fixed.txt`

仓库内对应索引入口：

- `docs/coordination/reports/delivery-report.md#r31-当前机器-r4-full-mode-等价环境实跑`

### 4.2 R5 审查包已纳入候选

以下文件已属于正式交付候选的一部分：

- `docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md`
- `docs/coordination/reports/delivery-report.md`
- `docs/coordination/TASK_BOARD.md`

因此当前分支上已经直接包含了：

- 最终审查包
- 审查状态
- 最终签字输入

---

## 5. 这份 manifest 的使用方式

推荐按下面顺序使用：

1. 用它确认“这次正式交付到底包含什么文件”；
2. 用 `R5_FINAL_REVIEW_PACKAGE.md` 看审查输入；
3. 用 `delivery-report.md#r33-最终签字记录块待-owner-确认` 做最后签字；
4. 用 PR #7 作为 GitHub 审查入口；
5. 用 `r4-evidence` 本地目录回查 current-machine rehearsal 细节。

---

## 6. 当前结论

> **本 manifest 固定的是：当前最新 candidate HEAD `0eb8644` 的正式交付文件边界。**
>
> **它的作用不是证明一切都完成，而是防止后续再把过程材料、归档材料、临时差异文件混进正式交付范围。**
