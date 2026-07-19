# TASK BOARD

## Board Meta

- 当前目标：`xagent` PR 审查准备 / 发布证据补齐，不扩新功能
- 唯一事实源：[COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md](../COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md)
- 发布门禁：[COMMERCIAL_RELEASE_CHECKLIST_V1.md](../COMMERCIAL_RELEASE_CHECKLIST_V1.md)
- 协作入口：[README.md](./README.md)
- 执行协议：[TASK_PACKAGE_PROTOCOL.md](./TASK_PACKAGE_PROTOCOL.md)
- 最后更新时间：2026-07-07
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

- [U2] 为 R4 生成 full-mode 环境恢复执行包 | 区域: coordination/rehearsal-unblock | 状态: DONE | Owner: Claude Code | 分支/工作树: `candidate/min-send-review-20260707-claude` / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R16(REVIEW) | 验收摘要: 在当前机器完成 isolated compose `xagent-r4` 等价环境实跑，验证 `/health`、`/ready`、`alembic current`、`xagent.cli smoke`、full-mode 显式账号与 `full-flow.spec.ts` 9/9，通过后形成 R31 交付记录 | 证据: reports/delivery-report.md#r31-当前机器-r4-full-mode-等价环境实跑
- [R5] PR 审查包组装与 reviewer 入口清理 | 区域: pr-packaging | 状态: DONE | Owner: Claude Code | 分支/工作树: `candidate/min-send-review-20260707-claude` / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R1(DONE),R4(当前机器等价环境已实跑),R8(REVIEW) | 验收摘要: `R5_FINAL_REVIEW_PACKAGE.md` 已形成并更新为最终候选 commit `c175201cdee1026d89be8d96b93c3f6bfa0f1739` 与远端 CI run `28921940625` 全绿口径；owner 已授权代为完成最终签字，当前已进入留档与环境收尾阶段 | 证据: reports/R5_FINAL_REVIEW_PACKAGE.md; reports/delivery-report.md#r32-r5-最终审查包当前候选; reports/delivery-report.md#r33-最终签字记录块owner-已确认

---

## Goal Board Entry

- 当前总 Goal：`G0 xagent 商用完整交付`
- 当前激活阶段：`G1 内部试点可稳定使用`
- 当前 active 包：`G1-A1 功能链路包`
- 当前 ready 包：`G1-A2 稳定性 / 恢复包`
- Goal 板文档：[`commercialization-goal-board.md`](reports/commercialization-goal-board.md)


> 阻塞格式：`[ID] 标题 | Owner | 阻塞原因 | 需要谁决策 | 恢复条件 | 下次检查点`

- [U-CODEX-20260706-2235] Codex R8/R15/R17/R18/R19 收尾链恢复执行记录 | Owner: Codex | 阻塞原因: 当前 Codex READY 包已清空；R18/R19 已领取并转 REVIEW，等待总调度验收、退回或补单 | 需要谁决策: Claude Code 总调度验收/退回 REVIEW 队列，或新增 Codex READY 包 | 恢复条件: 有新的 Codex READY 包，或 R8/R15/R17/R18/R19/R14/R16 任一 REVIEW 被退回并明确缺口 | 下次检查点: 任务板出现新 READY / REVIEW 退回 / 总调度指令后立即复检 | 证据: reports/delivery-report.md#r8-对外口径一致性终检包; reports/delivery-report.md#r15-任务板与交付证据一致性补齐; reports/delivery-report.md#r17-pr-证据矩阵源数据补齐; reports/delivery-report.md#r18-候选分支与-pr6-新鲜度审计; reports/delivery-report.md#r19-full-mode-凭据secret-交接模板包
  live: 2026-07-07T09:48:42+08:00 | substate: NO_CODEX_READY | action: 复核任务板与 delivery-report；当前无 Codex READY，R8/R14/R15/R16/R17/R18/R19 仍等待 REVIEW；R20 已更新为本地 `pytest -q` 复绿，R21 已新增候选冻结与 R4/R5 闭环清单，但任务板仍未给 Codex 新修复包 | risk: R20/R21 剩余风险仍是 R4 full-mode/目标环境演练 BLOCKED、R5 不能签发、当前工作树未冻结且远端 CI 只覆盖旧候选 `d59faa3`；Codex 不在无任务卡情况下越权处理 | next: Claude Code 总调度验收/退回 Codex REVIEW 队列，并决定是否需基于 R20/R21 剩余风险拆出新的 Codex READY 包；Codex 不接管 U2/R4/R5 | due: 2026-07-07T11:48:42+08:00 | detail: reports/delivery-report.md#r21-候选冻结--r4r5-闭环清单

---

## Ready for Review

> 完成自测后移到这里，并补：变更摘要 / 验证命令 / 风险 / reviewer 关注点

- [R19] full-mode 凭据/secret 交接模板包 | 区域: release/env-handoff | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-07T01:31:55+08:00 | 完成时间: 2026-07-07T01:34:56+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R16(REVIEW；任务卡原依赖写 R16(DONE)),U2(交付证据存在；不改 Claude Code 车道状态) | 变更摘要: 新增 R19 full-mode secret handoff template，覆盖候选绑定、secret/config 引用、full-mode 账号来源、端口与依赖、R4 recovery evidence checklist 和 reviewer checklist；不含真实 secret | 验证命令: template-structure `rg`; dangerous-value `rg`; `git diff --check -- docs\coordination\TASK_BOARD.md docs\coordination\reports\delivery-report.md docs\coordination\reports\R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md` | 风险: 不提供真实 secret、不启动 compose、不执行 smoke/E2E、不解除 R4/R5 gate；R16/U2 依赖标签漂移已保留 | Reviewer 关注点: 确认模板只收集 secret-store 引用和证明字段，不收集真实值；确认 R19 是 R4 恢复输入而非演练完成证据 | 证据: reports/delivery-report.md#r19-full-mode-凭据secret-交接模板包；reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md
  live: 2026-07-07T08:46:28+08:00 | substate: WAITING_REVIEW | action: REVIEW 等待心跳刷新，R19 仍等待 reviewer 验收无密交接模板和验证证据 | risk: 模板需由环境/发布负责人实际填写后才可恢复 R4；R19 不替代真实 secret 注入或 full-mode rehearsal | next: reviewer 确认模板字段是否足够，或退回缺少的 secret/账号/LLM/端口证明字段 | due: 2026-07-07T10:46:28+08:00 | detail: reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md
- [R18] 候选分支与 PR#6 新鲜度审计 | 区域: release/candidate-freshness | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-07T01:25:17+08:00 | 完成时间: 2026-07-07T01:30:34+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R1(DONE),R17(REVIEW；任务卡原依赖写 R17(DONE)，已作为依赖漂移风险记录) | 变更摘要: 新增 R18 candidate freshness audit，确认 PR #6 / `d59faa3` 远端 CI 只覆盖该候选，不覆盖当前本地 `HEAD=a98cea0` 与 54 tracked / 53 untracked 工作树差异；给出 R5 必须冻结新候选并重跑远端 CI 的判断 | 验证命令: `gh pr view 6 --json ...`; `git rev-parse HEAD`; `git status --short --branch`; `git merge-base HEAD d59faa3`; `git log --oneline --left-right --cherry-pick d59faa3...HEAD`; `git diff --name-status d59faa3..HEAD`; `git diff --name-status`; `git ls-files --others --exclude-standard`; `git diff --check -- ...` | 风险: 不决定哪些本地改动进入候选；不把 PR #6 CI 写成当前工作树 CI；不解除 R4/R5/R8/R15/R17 gate | Reviewer 关注点: 确认 R5 只能复用 PR #6 作为 `d59faa3` 的证据，若纳入当前本地工作树需新候选分支与新 CI | 证据: reports/delivery-report.md#r18-候选分支与-pr6-新鲜度审计；reports/R18_CANDIDATE_FRESHNESS_AUDIT.md
  live: 2026-07-07T08:46:28+08:00 | substate: WAITING_REVIEW | action: REVIEW 等待心跳刷新，R18 仍等待 reviewer 验收 candidate freshness 审计证据 | risk: 当前工作树非 PR#6 候选；R18 不替代新候选冻结或远端 CI | next: reviewer 确认 R18 结论是否足够作为 R5 输入，或退回具体 candidate freshness 缺口 | due: 2026-07-07T10:46:28+08:00 | detail: reports/R18_CANDIDATE_FRESHNESS_AUDIT.md
- [R17] PR 证据矩阵源数据补齐 | 区域: pr/evidence-matrix | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T22:30:14.5986179+08:00 | 完成时间: 2026-07-06T22:34:07.5161338+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R8(REVIEW),R10(DONE),R11(DONE),R12(DONE) | 变更摘要: 新增 R17 PR evidence matrix source，按发布检查表分区汇总 DONE/REVIEW 包证据、R5 使用提示与剩余风险；同步 ROADMAP R17 REVIEW；2026-07-07 补入 R18/R19 后续 READY 候选和依赖标签风险，显式保留 R17 REVIEW 边界 | 验证命令: `rg -n "Checklist Evidence Matrix|Evidence Index For R5|Remaining Risks..." docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md`; `rg -n "R17.*状态: REVIEW|R5.*PR 审查包|R4.*BLOCKED" ...`; recovery source/board `rg`; `git diff --check -- ...` | 风险: 不替代 R4、R5、发布检查表签字或正式 PR 文案；若 R5 候选包含 R13-R17 后续本地改动需重查远端 CI；R18/R19 不能被当成当前 gate 证据 | Reviewer 关注点: 确认矩阵保留 R4 BLOCKED、R8/R14/R15/R16/R17 REVIEW、R18/R19 依赖标签风险、R1 候选 CI 范围与 R11 audit 风险 | 证据: reports/delivery-report.md#r17-pr-证据矩阵源数据补齐；reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md
  live: 2026-07-07T08:46:28+08:00 | substate: WAITING_REVIEW | action: REVIEW 等待心跳刷新，R17 仍等待 reviewer 验收 PR 证据矩阵源数据 | risk: R17 只是 R5 输入源，不替代 PR 审查包、正式发布 gate、R18/R19 领取或依赖确认 | next: reviewer 确认通过或退回具体缺口；如需处理 R20 暴露的 pytest 失败，应由总调度另拆 READY 包 | due: 2026-07-07T10:46:28+08:00 | detail: reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md
- [R15] 任务板与交付证据一致性补齐 | 区域: coordination/evidence-sync | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T22:20:36.8428206+08:00 | 完成时间: 2026-07-06T22:27:04.7899394+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R8(REVIEW；如被退回需同步复核) | 变更摘要: 新增 R15 证据同步报告；R8 从过期 IN_PROGRESS 恢复为 REVIEW；R8 audit、delivery-report 与 ROADMAP 同步 R10/R11/R12/R13/R14/R15/R16/R17 当前状态；刷新过期 U-CODEX 等待记录；R17 后续已提交 REVIEW 并完成证据链补强；2026-07-07 记录 R5/U2 状态漂移修正与 R18/R19 依赖标签风险 | 验证命令: stale-status `rg`; board-status `rg`; release-message `rg`; `git diff --check -- docs\coordination\TASK_BOARD.md docs\coordination\reports\delivery-report.md docs\coordination\reports\R15_EVIDENCE_SYNC.md docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\ROADMAP.md` | 风险: 不替代总调度对 R8/R14/R16/R15/R17 的 REVIEW 验收；不解除 R4 BLOCKED；不签发 R5；不越权领取 R18/R19 | Reviewer 关注点: 确认 R8 状态修正有 delivery-report 与 R8 audit 证据支撑；确认 R17 已作为 PR 证据矩阵源数据进入 REVIEW，未被误写成 R5 最终 PR 审查包；确认 R18/R19 依赖标签漂移已暴露 | 证据: reports/delivery-report.md#r15-任务板与交付证据一致性补齐；reports/R15_EVIDENCE_SYNC.md
  live: 2026-07-07T08:46:28+08:00 | substate: WAITING_REVIEW | action: REVIEW 等待心跳刷新，R15 仍等待 reviewer 验收任务板与交付证据一致性补齐 | risk: R15 不替代 R8/R14/R16/R17 reviewer 结论，也不解除 R4 BLOCKED；R20 暴露的新 pytest 失败尚未拆 Codex READY | next: reviewer 可确认通过或指出仍漂移的任务/证据项；R20 修复如需 Codex 执行请总调度拆新包 | due: 2026-07-07T10:46:28+08:00 | detail: reports/R15_EVIDENCE_SYNC.md
- [R8] 对外口径一致性终检包 | 区域: docs/release-message | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T18:44:01.5095805+08:00 | 完成时间: 2026-07-06（R15/R17 状态同步确认） | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: COMMERCIAL_STATUS_SOURCE_OF_TRUTH,R1(DONE),R10(DONE),R11(DONE),R12(DONE) | 变更摘要: README / ROADMAP / 项目总览 / 接手说明与唯一事实源的发布口径已由 R8 收口；R15/R17 同步修正 R10/R11/R12/R13/R14/R15/R16/R17 后续状态；R8/R15/R17 证据链已无 R17 待领取旧口径 | 验证命令: `rg -n ... README.md docs\ROADMAP.md docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`; stale-R17-ready `rg`; `git diff --check -- ...` | 风险: 不替代 R4 目标环境演练、R5 PR 审查包、R14/R16/R15/R17 reviewer 验收或最终 PR 证据矩阵签发 | Reviewer 关注点: 确认当前口径未把正式商用 GA、R4、R5 或待审包写成完成；确认 R17 是 REVIEW 源数据而非 R5 最终 PR 包 | 证据: reports/delivery-report.md#r8-对外口径一致性终检包; ../RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md
  live: 2026-07-07T08:46:28+08:00 | substate: WAITING_REVIEW | action: REVIEW 等待心跳刷新，R8 仍等待 Claude Code 总调度验收对外口径一致性终检 | risk: R8 不能把 PR 审查准备误写成正式商用可交付，也不解除 R4/R5 gate | next: reviewer 可确认 R8 通过或退回具体文档/表述；R20 pytest 失败不属于 R8 口径包内修复 | due: 2026-07-07T10:46:28+08:00 | detail: ../RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md
- [R16] full-mode 演练前置条件补齐包 | 区域: release/rehearsal-prep | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T21:29:15+08:00 | 完成时间: 2026-07-06T21:34:00+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R4（可并行预研） | 变更摘要: 新增 full-mode rehearsal 前置清单，覆盖 `LANGFUSE_*`、JWT secret、显式账号、端口、依赖服务、LLM 路径、compose config 与 R4 恢复步骤 | 验证命令: `docker compose --env-file .env.example config --quiet`; 补齐 R16 演练占位 secret 后复跑 config; `Get-NetTCPConnection -LocalPort 5432,6379,6333,6334,3001,4000,8080,8081`; `rg -n "R16|LANGFUSE_NEXTAUTH_SECRET|full-mode|E2E_USERNAME|不启动 compose|不等于 R4" ...`; `git diff --check -- ...` | 风险: 不替代 R4 目标环境实跑、真实 secret manager、账号初始化、迁移、E2E/smoke 或 R5 PR 签发 | Reviewer 关注点: 确认清单是 R4 恢复输入而非演练完成证据；确认未把 `admin/admin` 用作 full-mode 账号 | 证据: reports/delivery-report.md#r16-full-mode-演练前置条件补齐包; reports/R16_FULL_MODE_REHEARSAL_PREP.md
  live: 2026-07-07T08:46:28+08:00 | substate: WAITING_REVIEW | action: REVIEW 等待心跳刷新，R16 仍等待 Claude Code 总调度验收 full-mode 演练前置清单 | risk: R16 只是 R4 恢复输入，不代表 full-mode 演练完成；不能解除 R4/R5 gate | next: reviewer 确认清单足够生成/支持 U2/R4 恢复执行，或退回缺口 | due: 2026-07-07T10:46:28+08:00 | detail: reports/R16_FULL_MODE_REHEARSAL_PREP.md
- [R14] Vite chunk warning 根因定位与最小拆包建议 | 区域: web/perf-bundle | 状态: REVIEW | Owner: Codex | 开始时间: 2026-07-06T21:06:08.2730854+08:00 | 完成时间: 2026-07-06T21:14:15+08:00 | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R11(DONE) | 变更摘要: `App.tsx` 改为路由级 `React.lazy` / `Suspense` 拆包，清除 Vite 500k chunk warning；最大 JS chunk 降至 294.19 kB / gzip 96.09 kB | 验证命令: `npm run lint`; `npm run typecheck`; `node --test tests/chatStream.test.mjs`; `npm run build`; `npx playwright test specs/full-flow.spec.ts --project=chromium` | 风险: 不替代全量 npm audit 依赖升级、真实性能压测、R4 目标环境演练或 R5 PR 审查包 | Reviewer 关注点: 确认未提高 Vite chunk 阈值或升级 Vite major；确认关键路由懒加载后 full-flow 9/9 仍通过 | 证据: reports/delivery-report.md#r14-vite-chunk-warning-根因定位与最小拆包建议; reports/R14_VITE_CHUNK_SPLIT.md
  live: 2026-07-07T08:46:28+08:00 | substate: WAITING_REVIEW | action: REVIEW 等待心跳刷新，R14 仍等待 Claude Code 总调度验收 Vite chunk 拆包结果 | risk: R14 不替代全量依赖升级、性能压测或 R4/R5 gate | next: reviewer 确认拆包证据与 full-flow 结果是否足够，或退回具体缺口 | due: 2026-07-07T10:46:28+08:00 | detail: reports/R14_VITE_CHUNK_SPLIT.md

---

## Done

> 已验收任务保留最近 7-14 天，并附交付记录链接

- [R13] Chat SSE 完成态 / 回退闭环修复并复绿 full-flow | 区域: runtime/chat-e2e | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R10(DONE) | 验收摘要: Chat SSE done/fallback 闭环已修复；full-flow 已提升为 9/9 通过；未把本地证据误写成正式发布 gate | 证据: reports/delivery-report.md#r13-chat-sse-完成态--回退闭环修复并复绿-full-flow
- [R1] 远端 CI 全绿收口与失败项清零 | 区域: remote-ci/gate | 状态: DONE | Owner: Claude Code | 分支/工作树: worktree-r1-remote-ci / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.claude\worktrees\r1-remote-ci` | 依赖: U1(DONE), Owner 决策=隔离后推送 | 验收摘要: fresh 候选 `d59faa3` 已通过 draft PR #6 的远端 CI（backend/frontend/license-gate/promptfoo-eval 全绿），R1 远端 CI 收口完成 | 证据: reports/delivery-report.md#r1-远端-ci-全绿收口与失败项清零
- [R2] frontend build 可复现验证与构建门禁补齐 | 区域: web/build | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: U1（仅远端 CI 同步） | 验收摘要: frontend build 在干净环境可稳定通过；CI 已补入 `npm run build` 门禁，真实状态文档与发布检查表口径同步更新 | 证据: reports/delivery-report.md#r2-frontend-build-可复现验证与构建门禁补齐
- [R3] 关键 E2E 冒烟包补齐并跑通 | 区域: e2e/core-flows | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R2(DONE) | 验收摘要: creative smoke 已补齐登录、canvas run → Run Console、媒体任务轮询证据；最小后端回归测试已通过 | 证据: reports/delivery-report.md#r3-关键-e2e-冒烟包补齐并跑通
- [R6] 发布/回滚 Runbook v1 补齐 | 区域: release/runbook | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: COMMERCIAL_RELEASE_CHECKLIST_V1 未勾选项 | 验收摘要: RELEASE_RUNBOOK_V1 已形成并覆盖发布/回滚/Smoke/异常处置；未把环境演练误写成已完成 | 证据: reports/delivery-report.md#r6-发布回滚-runbook-v1-补齐
- [R7] 环境基线与 secret 注入说明补齐 | 区域: ops/env-baseline | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: COMMERCIAL_STATUS_SOURCE_OF_TRUTH | 验收摘要: ENVIRONMENT_BASELINE_V1 已补齐环境分层、secret 注入、危险默认值禁用策略；未伪装目标环境 secret manager 已落地 | 证据: reports/delivery-report.md#r7-环境基线与-secret-注入说明补齐
- [R9] 关键页面截图/验收记录补齐 | 区域: qa/visual-evidence | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R2(DONE) | 验收摘要: 登录、对话/工作台、工作流、Run Console、设置页 5 张本地截图与验收记录已归档，并映射到发布检查表证据入口 | 证据: reports/delivery-report.md#r9-关键页面截图验收记录补齐
- [R10] full-flow E2E 补齐与差异归因 | 区域: e2e/full-flow | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R3(DONE) | 验收摘要: full-flow 已完成差异归因；当前证据为 8/9 通过、1 条 Chat SSE 完成态阻断已结构化定位，未把差异归因误写成全量通过 | 证据: reports/delivery-report.md#r10-full-flow-e2e-补齐与差异归因
- [R11] npm audit 与前端构建风险处置包 | 区域: web/deps-bundle | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R2(DONE) | 验收摘要: 已区分全量 npm audit 与生产依赖风险面，明确 chunk warning 非 build gate 阻断，并沉淀处置建议 | 证据: reports/delivery-report.md#r11-npm-audit-与前端构建风险处置包
- [R12] SQLite/Alembic 漂移诊断与复验指南 | 区域: db/dev-env | 状态: DONE | Owner: Codex | 分支/工作树: master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent` | 依赖: R3(DONE) | 验收摘要: 已确认本地 SQLite `0007` 漂移为历史库问题，fresh DB 迁移正常，并给出复验/处置指南 | 证据: reports/delivery-report.md#r12-sqlitealembic-漂移诊断与复验指南
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
