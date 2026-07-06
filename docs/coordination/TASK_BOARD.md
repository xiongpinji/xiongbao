# TASK BOARD

## Board Meta

- 当前目标：`xagent` PR 审查准备 / 发布证据补齐，不扩新功能
- 唯一事实源：[COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md](../COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md)
- 发布门禁：[COMMERCIAL_RELEASE_CHECKLIST_V1.md](../COMMERCIAL_RELEASE_CHECKLIST_V1.md)
- 协作入口：[README.md](./README.md)
- 执行协议：[TASK_PACKAGE_PROTOCOL.md](./TASK_PACKAGE_PROTOCOL.md)
- 最后更新时间：2026-07-06
- 当前总调度：Claude Code
- 当前发布口径：**P0-A 到 P0-E 已完成任务板收口；现阶段进入 PR 审查准备 / 发布证据补齐；不可直接宣称正式商用可交付，合并 / 发布仍需远端 CI 全绿、frontend build、关键 E2E 与环境演练证据**

### 协作规则速记

- 先领取再改动
- 一包一责任人
- 跨包修改要显式声明
- 未附证据不得转 `REVIEW`
- 阻塞超过 30 分钟必须写入 `Blocked`
- 主调度必须持续补单，维持 Codex 至少 2 张 `READY` 卡、Claude Code 至少 1 张当前/解阻卡

---

## Ready to Claim

- [R4] 目标环境演练与发布证据归档 | 区域: release-evidence | 状态: READY | Owner: Claude Code/运维协同 | 分支/工作树: 待填 | 依赖: R1,R2,R3,R6,R7,R9 | 验收摘要: 至少一次目标环境演练完成，含步骤、结果、异常与回滚/处置证据 | 证据: 待填
- [R5] PR 审查包组装与 reviewer 入口清理 | 区域: pr-packaging | 状态: READY | Owner: Claude Code | 分支/工作树: 待填 | 依赖: R1,R2,R3,R4,R8 | 验收摘要: PR 描述、风险摘要、验证矩阵、证据链接、reviewer 关注点齐全，可直接送审 | 证据: 待填

---

## In Progress

> 领取后把任务卡整体移到这里，并补齐 Owner / 开始时间 / 分支或工作树 / 预计交付。

- [R9] 关键页面截图/验收记录补齐 | 区域: qa/visual-evidence | 状态: CLAIMED | Owner: Codex | 开始时间: 2026-07-06T18:55:26.2998077+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R2 | 预计交付: 登录、对话/工作台、工作流、Run Console、设置页形成截图或等价验收记录，归档到发布证据并映射发布检查表。
- [R1] 远端 CI 全绿收口与失败项清零 | 区域: remote-ci/gate | 状态: IN_PROGRESS | Owner: Claude Code | 开始时间: 2026-07-06 18:22:20 +08:00 | 分支/工作树: worktree-r1-remote-ci / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.claude\worktrees\r1-remote-ci` | 依赖: U1(DONE), Owner 决策=隔离后推送 | 预计交付: 在 fresh readiness 工作树中整理可推送候选、触发当前候选远端 CI，并回填 gate 结果证据。

---

## Blocked

> 阻塞格式：`[ID] 标题 | Owner | 阻塞原因 | 需要谁决策 | 恢复条件 | 下次检查点`

暂无。

---

## Ready for Review

> 完成自测后移到这里，并补：变更摘要 / 验证命令 / 风险 / reviewer 关注点

- [R8] 对外口径一致性终检包 | 区域: docs/release-message | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T18:44:01.5095805+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: COMMERCIAL_STATUS_SOURCE_OF_TRUTH | 变更摘要: README、ROADMAP、项目总览、接手说明与唯一事实源的当前发布口径已对齐；新增 R8 终检记录与差异清单 | 验证命令: 旧口径残留 `rg`; SOT/R8 关联 `rg`; `git diff --check`; trailing whitespace scan | 风险: 不包含远端 CI、目标环境演练、PR 审查包或页面截图证据 | Reviewer 关注点: 验证历史完成态没有被误写成当前正式 GA，且 R1/R4/R5/R9 未被提前宣称完成 | 证据: reports/delivery-report.md#r8-对外口径一致性终检包
- [R2] frontend build 可复现验证与构建门禁补齐 | 区域: web/build | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T17:54:13.7836770+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: U1（仅远端 CI 同步） | 变更摘要: 前端 CI job 新增 `npm run build`；发布检查表与唯一事实源同步 frontend build 证据口径 | 验证命令: `npm ci`; `npm run lint`; `npm run typecheck`; `npm run build`; `git diff --check -- ...` | 风险: 当前工作树远端 CI 仍未闭环；npm audit 仍提示 1 moderate / 1 high；Vite chunk size warning 仍存在 | Reviewer 关注点: 验证 R2 未扩展到 R1/R3，且未提前勾选发布检查表 | 证据: reports/delivery-report.md#r2-frontend-build-可复现验证与构建门禁补齐
- [R3] 关键 E2E 冒烟包补齐并跑通 | 区域: e2e/core-flows | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T18:00:17.6202230+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R2（若 R2 被退回，本包需同步复核） | 变更摘要: Playwright creative smoke 补齐登录、canvas run 到 Run Console、媒体任务轮询；canvas run 持久化 workflow view 以修复 `/runs/{workflow_run_id}` 404；新增后端最小回归测试 | 验证命令: `ruff check ...`; `pytest ...::test_canvas_run_persists_workflow_for_run_console`; `pytest tests/test_e2e_drama_canvas.py`; `npm ci`; `npx playwright test specs/creative-smoke.spec.ts --project=chromium` | 风险: 远端 CI 未闭环；full-flow 未运行；本地旧 SQLite revision 漂移未在本包修复 | Reviewer 关注点: 验证后端跨包触及仅限 canvas workflow view 持久化，且 R3 未宣称完整发布验收 | 证据: reports/delivery-report.md#r3-关键-e2e-冒烟包补齐并跑通
- [R6] 发布/回滚 Runbook v1 补齐 | 区域: release/runbook | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T18:32:19.3074119+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: COMMERCIAL_RELEASE_CHECKLIST_V1 未勾选项 | 变更摘要: 新增 `docs/RELEASE_RUNBOOK_V1.md`，补齐发布 gate、构建、DB 备份/迁移、Compose 发布、smoke、回滚、异常处置与证据模板；部署 Runbook 与唯一事实源补入口径 | 验证命令: `Test-Path`; `rg` 关键章节；`rg RELEASE_RUNBOOK_V1`; `git diff --check`; trailing whitespace scan | 风险: 未执行目标环境演练；远端 CI 仍由 R1 处理；K8s/HA 不在 v1 范围 | Reviewer 关注点: 验证 R6 未把 runbook 文档就绪误写成发布演练完成，且未勾选发布检查表 | 证据: reports/delivery-report.md#r6-发布回滚-runbook-v1-补齐
- [R7] 环境基线与 secret 注入说明补齐 | 区域: ops/env-baseline | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T18:38:28.8074263+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: COMMERCIAL_STATUS_SOURCE_OF_TRUTH | 变更摘要: 新增 `docs/ENVIRONMENT_BASELINE_V1.md`，明确 dev/staging/prod 基线、secret 清单、compose/Helm 注入、危险默认值禁用策略与剩余缺口；发布检查表、Runbook 与唯一事实源补入口径 | 验证命令: `Settings.validate_for_production`; `docker compose ... config`; `helm template`; `Test-Path`; `rg` 关键章节与引用 | 风险: 真实 secret manager / secretRef 接入未演练；POSTGRES 示例密码需目标环境覆盖；远端 CI 由 R1 处理 | Reviewer 关注点: 验证 R7 未伪装 secret manager / secretRef 已落地，且未勾选发布检查表 | 证据: reports/delivery-report.md#r7-环境基线与-secret-注入说明补齐

---

## Done

> 已验收任务保留最近 7-14 天，并附交付记录链接

- [U1] 为 R1 生成远端 CI 决策与解阻包 | 区域: coordination/unblock | 状态: DONE | Owner: Claude Code | 分支/工作树: master / workspace | 依赖: 无 | 验收摘要: 已明确 readiness 候选不能直接推送脏的本地 `master`；Owner 已选择“隔离后推送”，R1 可恢复执行 | 证据: reports/delivery-report.md#u1-为-r1-生成远端-ci-决策与解阻包
- [P0-E] CI 最小门禁与真实状态文档对齐 | 区域: ci/docs | 状态: DONE | Owner: Claude Code | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: P0-A(DONE),P0-B(DONE),P0-C(DONE),P0-D(DONE) | 验收摘要: CI 新增前端 lint/typecheck 最小门禁；后端 ruff/pytest 门禁保留；真实状态文档和发布检查表同步 2026-07-06 readiness 口径 | 证据: reports/delivery-report.md#p0-e-ci-最小门禁与真实状态文档对齐
- [P0-C] preview/demo 污染清理 | 区域: web/pages | 状态: DONE | Owner: Claude Code | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: P0-B(DONE) | 验收摘要: 正式路径不再依赖 fallbackRoles / 本地预览提示 / 默认 demo workflow | 证据: reports/delivery-report.md#p0-c-previewdemo-污染清理
- [P0-B] 前端 lint 阻断 | 区域: web/tests | 状态: DONE | Owner: Claude Code | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: 无 | 验收摘要: `npm run lint` 已通过，未降低 ESLint 强度 | 证据: reports/delivery-report.md#p0-b-前端-lint-阻断
- [P0-D] 危险默认值清零 | 区域: security/config/deploy | 状态: DONE | Owner: Claude Code | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: 无 | 验收摘要: full/enterprise 默认 admin、弱 JWT、compose/Helm/Keycloak 弱默认已改为显式配置或 fail-fast | 证据: reports/delivery-report.md#p0-d-危险默认值清零
- [P0-A] orchestration await bug | 区域: backend/runtime | 状态: DONE | Owner: Claude Code | 分支/工作树: master / workspace | 依赖: 无 | 验收摘要: `loop.py` 提示工程 tool fallback 分支已补 `await`，最小回归测试与既定验证集已复跑通过 | 证据: reports/delivery-report.md#p0-a-orchestration-await-bug

---

## 任务卡模板

```text
[ID] [P0/P1] 标题 | 区域 | 状态 | Owner(Claude/Codex/人工) | 分支/工作树 | 依赖 | 验收摘要 | 证据链接
```

### 示例

```text
[P0-B] 前端 lint 阻断 | web/tests | IN_PROGRESS | Owner: Codex | branch: fix/p0-b-lint | 依赖: 无 | 验收摘要: npm run lint 绿，且未降低 eslint 强度 | 证据: reports/delivery-report.md#p0-b
```
