# Delivery Report

> 规则：一包一节，按时间倒序追加。
> 这里只记录交付结果、证据、遗留风险，不把任务板写成流水账。

---

## 模板

### [任务包 ID]

- 交付人：
- 日期：
- 关联分支 / 工作树：
- 变更摘要：
- 验证命令：
- 验证结果：
- Reviewer 关注点：
- 剩余风险：
- 关联提交 / PR：
- 证据：

---

### [R32] R5 最终审查包（当前候选）

- 交付人：Claude Code
- 日期：2026-07-08
- 关联分支 / 工作树：`candidate/min-send-review-20260707-claude` / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md`，将候选分支、PR、远端 CI、R4 当前机器等价环境实跑、交付材料与剩余风险收敛为一份 reviewer / owner 可直接使用的最终审查包。
  - 明确区分“当前候选分支已有远端 CI 绿色记录”和“当前本地新增收口改动尚未被新的远端 CI 覆盖”的边界，避免错误放大证据范围。
  - 给出最终发布判断的三档建议：试点/受控交付可成立、当前本地闭环状态可送审但需冻结并重跑 CI、正式商用可交付取决于 owner 是否接受当前机器等价环境与单人签字模式。
- 验证命令：
  - 交叉核对 `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - 交叉核对 `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
  - 交叉核对 `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
  - 交叉核对 `docs/coordination/reports/delivery-report.md#r31-当前机器-r4-full-mode-等价环境实跑`
  - 交叉核对 `docs/DELIVERY_MATERIALS_INDEX_V1.md`
  - `git status --short --branch`
- 验证结果：
  - R5 最终审查包已具备候选范围、验证矩阵、reviewer 关注点、剩余风险、发布判定建议与最终 owner 检查单。
  - R5 没有把“当前本地已收口”直接伪装成“已被远端 CI 覆盖”；文中显式保留了重新冻结并重跑 CI 的前提。
  - R5 已把当前单人交付模式纳入最终判定条件，不再错误地把“缺联系人”作为当前单人模式下的独立阻断。
- Reviewer 关注点：
  - 确认本包用于最终判断与签发，不是自动发布命令。
  - 确认正式商用可交付的建议依赖于 owner 是否接受当前机器等价环境与单人签字模式。
  - 确认仍未跳过“冻结本地收口改动并重跑远端 CI”这一步。
- 剩余风险：
  - 当前本地新增收口改动尚未形成新的远端 CI 证据。
  - 若你不接受当前机器作为正式交付环境/等价环境，则仍需其他目标环境复演。
  - 最终是否判定为正式商用可交付，仍取决于 owner 的明确接受与签字。
- 关联提交 / PR：PR #7（candidate/min-send-review-20260707-claude）
- 证据：`docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md`；`docs/coordination/reports/delivery-report.md#r31-当前机器-r4-full-mode-等价环境实跑`

---

### [R31] 当前机器 R4 full-mode 等价环境实跑

- 交付人：Claude Code
- 日期：2026-07-08
- 关联分支 / 工作树：`candidate/min-send-review-20260707-claude` / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 在当前机器上使用 isolated compose 项目 `xagent-r4` 执行一轮 full-mode 等价环境演练，避免污染默认 `xagent` 栈。
  - 通过运行时生成的本地 secret 拉起 `postgres`、`redis`、`qdrant`、`litellm`、`langfuse`、`api`、`worker`、`web`，并验证 `/health`、`/ready`、`alembic current`、`python -m xagent.cli smoke`、显式 full-mode 账号注册和 `full-flow.spec.ts`。
  - 根因排查并收口了两处真实阻断：`deploy/compose/postgres-init.sh` 的 CRLF shebang 问题，以及 worker 继承 API 健康检查导致的伪失败；full-flow 唯一失败项进一步定位为 Run Console replay/resume 区块中重复 task path 文本导致的严格选择器误报，并以最小范围收紧测试断言后复绿。
- 验证命令：
  - `docker compose -p xagent-r4 ... up -d --build`
  - `curl http://localhost:8000/health`
  - `curl http://localhost:8000/ready`
  - `docker exec xagent-r4-api-1 python -m alembic current`
  - `docker exec xagent-r4-api-1 python -m xagent.cli smoke`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium`
- 验证结果：
  - `compose ps`：`api` healthy，`postgres/redis/qdrant` healthy，`web`/`worker` running，isolated stack 正常存活。
  - `/health`：200，返回 `{"status":"ok","version":"0.1.0"}`。
  - `/ready`：200，返回 `ready=true`，database/cache healthy。
  - `alembic current`：`0005 (head)`。
  - `python -m xagent.cli smoke`：PASS，三链路全通。
  - full-mode 显式账号：现场注册成功，并能用于 API / Playwright 登录。
  - `full-flow.spec.ts --project=chromium`：9/9 通过。
- Reviewer 关注点：
  - 确认本次 R4 证据属于当前机器上的单机 compose 等价环境实跑，不自动外推为客户现场或其他目标环境签字。
  - 确认 worker 健康检查修复是针对已确认根因的最小配置修复，而不是范围外功能改动。
  - 确认 full-flow 唯一失败项属于测试 strict selector 与重复文本节点冲突，不是主链运行失败。
- 剩余风险：
  - 当前仍缺真实交付环境中的实名联系人、最终签字与客户目标环境演练签收。
  - 这轮演练使用的是运行时本地生成 secret，不应当作长期环境凭据保存或复用。
  - R5 PR 审查包仍需把本轮 R4 证据正式挂接并由你最终确认发布口径。
- 关联提交 / PR：PR #7（candidate/min-send-review-20260707-claude）
- 证据：`C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\compose-ps.txt`；`C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\alembic-current.txt`；`C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\api-smoke.txt`；`C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\full-flow-fixed.txt`

---

### [R30] 正式交付剩余外部条件与 R4 环境输入清单

- 交付人：Claude Code
- 日期：2026-07-08
- 关联分支 / 工作树：`candidate/min-send-review-20260707-claude` / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/FORMAL_RELEASE_EXTERNAL_CONDITIONS_V1.md`，把当前正式交付剩余阻断明确收敛为外部条件：R4 环境演练、R5 签发级证据、真实联系人、最终签字。
  - 文档中显式列出 R4 必需输入：候选绑定信息、必填 secret 来源、full-mode 显式账号、至少一条 LLM 路径、依赖服务与端口状态，以及完成后必须回传的日志 / smoke / E2E / 回滚证据。
  - 把“现在可以直接发给环境 / 发布负责人”的最小请求文案固化，避免继续围绕代码层重复沟通。
  - 同步将 `R20_FINAL_WRAP_UP_DELIVERY.md` 的相关证据入口补入交付材料索引、管理员部署手册、运维手册、已知问题/试点边界、支持升级路径和本次外部条件清单。
- 验证命令：
  - 交叉核对 `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
  - 交叉核对 `docs/RELEASE_RUNBOOK_V1.md`
  - 交叉核对 `docs/DELIVERY_MATERIALS_INDEX_V1.md`
  - 交叉核对 `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
  - `git diff --check -- docs/FORMAL_RELEASE_EXTERNAL_CONDITIONS_V1.md docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - R30 已把“当前还差什么”压缩为单页外部条件清单，明确当前剩余阻断不再是代码功能问题。
  - R30 保留了与现有准绳一致的边界：不把 lite/dev 证据写成目标环境演练完成，不把角色占位表写成真实联系人，不把 R5 / 最终签字写成已完成。
  - `R20_FINAL_WRAP_UP_DELIVERY.md` 的证据入口已补上交付材料包与外部条件清单，便于 reviewer / 发布负责人统一检索。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R30 的作用是压缩外部依赖与环境输入，不是宣称正式交付已经闭环。
  - 确认文档要求提供 secret 来源而不是把真实 secret 写入 Git。
  - 确认新增材料入口与最终收尾文档口径一致，没有把“试点可交付”升级表述成“正式商用已签发”。
- 剩余风险：
  - R4 仍需环境 / 发布负责人实际提供 full-mode secret、账号、依赖、LLM 路径并完成实跑。
  - R5 仍需基于 R4 证据、reviewer 验收与最终签字输入才能进入可签发状态。
  - 真实联系人与值守信息仍待具体交付环境补齐。
- 关联提交 / PR：PR #7（candidate/min-send-review-20260707-claude）
- 证据：`docs/FORMAL_RELEASE_EXTERNAL_CONDITIONS_V1.md`；`docs/DELIVERY_MATERIALS_INDEX_V1.md`；`docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`

---

### [R28] 候选冻结前执行检查单

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R28_CANDIDATE_FREEZE_PRE_EXEC_CHECKLIST.md`，把已决范围与精确暂存清单进一步转换为真正冻结前可逐条执行的检查单。
  - 将真正冻结前的动作拆为：确认目标、排除项不进候选、暂存 A 组、暂存 B 组、确认拍板项未误入 staged set、检查 staged set 与验证口径。
  - 明确只有在上述步骤全部完成后，才可进入 branch / commit / push / 远端 CI 绑定动作。
- 验证命令：
  - 交叉核对 `docs/coordination/reports/R27_DECIDED_FREEZE_SCOPE_MEMO.md`
  - 交叉核对 `docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`
  - `git diff --check -- docs/coordination/reports/R28_CANDIDATE_FREEZE_PRE_EXEC_CHECKLIST.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - R28 已将冻结前的执行顺序收敛为 checklist，可直接用于 staged candidate 前的逐条核对。
  - R28 保持与 R27 / R26 / R25 口径一致：先范围拍板，后 staged candidate，再 branch / commit / 远端 CI 绑定。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R28 是执行前检查单，不是冻结已完成的证据。
  - 确认 R28 没有跳过 staged set 检查步骤。
  - 确认 R28 仍然保留 R4 / R5 未完成这一边界。
- 剩余风险：
  - 当前仍未真正执行 staged candidate。
  - 当前仍未创建候选 branch / commit，也未绑定新的远端 CI。
  - R4 / R5 gate 仍未解除。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R28_CANDIDATE_FREEZE_PRE_EXEC_CHECKLIST.md`；`docs/coordination/reports/R27_DECIDED_FREEZE_SCOPE_MEMO.md`；`docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`

---

### [R27] 已决冻结范围说明

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R27_DECIDED_FREEZE_SCOPE_MEMO.md`，将 R26 的默认 YES / NO 建议固化为一份“已决冻结范围说明”。
  - 明确本轮按默认建议采用“最小可送审候选”模式：`ci.yml` 纳入，Helm / Keycloak / R16 / R17 / R19 / R9 / 视觉证据型 E2E 不纳入本轮最小候选。
  - 将范围讨论正式结束，后续执行链切换为：按 R25 形成 staged candidate，再进入 branch / commit / 远端 CI 绑定。
- 验证命令：
  - 交叉核对 `docs/coordination/reports/R26_YES_NO_DECISION_SHEET_FOR_CANDIDATE_FREEZE.md`
  - 交叉核对 `docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`
  - `git diff --check -- docs/coordination/reports/R27_DECIDED_FREEZE_SCOPE_MEMO.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - R27 已把默认拍板建议固定为明确的 YES / NO 结果，当前候选范围不再依赖口头约定。
  - R27 明确本轮采用最小可送审候选，不把扩展证据包与额外部署边界自动并入。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R27 只是“范围已决”，不是冻结已完成。
  - 确认 R27 与 R26 / R25 / R24 的顺序一致：先拍板，后 staged，再 branch / commit / CI。
  - 确认 R27 不把 R4 / R5 误写成已完成。
- 剩余风险：
  - 当前仍未真正形成 staged candidate。
  - 当前仍未固定 branch / commit，也未绑定新的远端 CI。
  - R4 / R5 gate 仍未解除。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R27_DECIDED_FREEZE_SCOPE_MEMO.md`；`docs/coordination/reports/R26_YES_NO_DECISION_SHEET_FOR_CANDIDATE_FREEZE.md`；`docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`

---

### [R26] 候选冻结 YES/NO 拍板清单

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R26_YES_NO_DECISION_SHEET_FOR_CANDIDATE_FREEZE.md`，把当前最小候选冻结前的未决范围问题压缩成 10 项 YES / NO 拍板清单。
  - 为每个拍板项给出默认建议，并说明 YES / NO 各自意味着候选范围如何变化。
  - 进一步把“最小可送审候选”和“完整内部 dossier”两种模式的边界讲清楚，方便负责人快速做范围决策。
- 验证命令：
  - 交叉核对 `docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`
  - 交叉核对 `docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`
  - `git diff --check -- docs/coordination/reports/R26_YES_NO_DECISION_SHEET_FOR_CANDIDATE_FREEZE.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - R26 已把候选冻结前仍未决的边界收敛为 10 个 YES / NO 决策项，可直接用于负责人拍板。
  - R26 默认建议保持最小可送审候选路线：`ci.yml` YES，Helm / Keycloak / R16 / R17 / R19 / R9 / 视觉证据型 E2E 默认为 NO。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R26 是拍板清单，不是冻结结果。
  - 确认 R26 的默认建议足够保守，避免在未决时把扩展边界压进候选。
  - 确认 R26 与 R25 / R24 的口径一致：先拍板，再冻结。
- 剩余风险：
  - 只要这些 YES / NO 还没正式拍板，R25 仍不能直接转成最终 staged candidate。
  - 即使拍板完成，后续仍需真正执行 branch / commit / 远端 CI 绑定。
  - R4 / R5 gate 仍未解除，拍板清单本身不改变发布 readiness 状态。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R26_YES_NO_DECISION_SHEET_FOR_CANDIDATE_FREEZE.md`；`docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`；`docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`

---

### [R25] 最小候选精确暂存清单

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`，将 R24 的冻结动作单进一步落为“精确暂存文件列表”。
  - 把本轮最小可送审候选拆成 A 组（代码 / 测试 / 运行配置）与 B 组（最小 release/readiness 文档主干），便于冻结前分批暂存和核对。
  - 明确列出本轮不要暂存的文件，以及仍需负责人拍板的 Helm / Keycloak / 扩展证据包，避免真正冻结时误入 staged set。
- 验证命令：
  - 交叉核对 `docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`
  - 交叉核对 `docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`
  - `git diff --check -- docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - R25 已将“最小可送审候选”的建议范围收敛为精确文件级暂存清单，可直接作为冻结前 staged 参考。
  - R25 将 staged 范围清楚拆为 A 组与 B 组，并保留排除项与待拍板项，避免真正冻结时继续混入运行产物或扩展证据包。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R25 是精确暂存清单，不是已完成 `git add` 的结果。
  - 确认 R25 没有把待拍板项默认压进最小候选。
  - 确认 R25 的 A / B 分组足够支持后续真正冻结 branch / commit。
- 剩余风险：
  - R25 只解决“现在该暂存什么”，不替代真正 branch / commit / CI 绑定。
  - Helm / Keycloak / 扩展证据包仍待拍板。
  - R4 / R5 gate 仍未解除，形成 staged candidate 也不等于可直接发布。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R25_EXACT_STAGING_LIST_MINIMAL_CANDIDATE.md`；`docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`；`docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`

---

### [R24] 候选冻结动作单

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`，把 R23 的“最小可送审候选文件集”进一步收敛为可执行冻结动作单。
  - 明确了真正冻结前的执行纪律：不要 `git add .`，先排除日志/snapshot/过程材料，再分组暂存代码测试组与文档主干组。
  - 将 Helm / Keycloak / R16/R17/R19 / R9 等内容保留为单独拍板项，避免在负责人未确认前扩大候选边界。
  - 给出默认拍板建议：`ci.yml` YES，Helm/Keycloak NO，R16/R17/R19/R9 先不进最小候选，优先形成最小可送审候选后再绑定 branch / commit / CI。
- 验证命令：
  - 交叉核对 `docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`
  - 交叉核对 `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`
  - `git diff --check -- docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - R24 已把冻结动作从“口径层建议”收敛为“先排除、再分组暂存、后拍板、最后固定 branch/commit/CI”的执行顺序。
  - R24 明确禁止在当前脏工作树上直接 `git add .`，避免日志、snapshot、过程材料与拍板项误入候选。
  - R24 保留了真正冻结后的正确顺序：候选冻结 → 远端 CI → R4 → R5。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R24 是冻结动作单，不是已完成冻结的证明。
  - 确认 R24 没有跳过拍板项，也没有把 R4 / R5 提前写成完成。
  - 确认 R24 的默认建议足够保守，能先形成最小可送审候选。
- 剩余风险：
  - 当前 branch / commit 尚未真正固定，远端 CI 也未重新绑定到新候选。
  - Helm / Keycloak / 扩展证据包仍需负责人拍板。
  - R4 / R5 gate 仍未解除，R24 只解决“如何冻结”，不解决“冻结后是否可发布”。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`；`docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`；`docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`

---

### [R23] 最小可送审候选文件集

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`，把 R22 的 Include / Exclude / Needs decision 进一步收敛成“最小可送审候选文件集”。
  - 明确最小候选默认包含：真实产品代码与测试、必要静态资源、关键 CI / compose 配置、最小 release/readiness 文档主干。
  - 明确最小候选默认不包含：日志、snapshot、一次性审计笔记、FRONTEND_* 过程文档、superpowers/plans、coordination 协议文档，以及扩展证据包。
  - 将 Helm / Keycloak / 视觉证据 / R16/R17/R19 等内容保留为拍板项或扩展审查包，而不默认压进最小送审候选。
- 验证命令：
  - 交叉核对 `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`
  - 交叉核对 `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`
  - `git diff --check -- docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - R23 已将当前工作树收敛为可执行的“最小送审候选”集合，避免在真正冻结前继续混入日志、快照、过程材料和扩展证据包。
  - R23 将 `.github/workflows/ci.yml` 视为建议随候选一起冻结的关键文件，以确保候选与后续远端 CI 定义一致。
  - R23 明确将 Helm / Keycloak / R16/R17/R19 / R9 视觉证据等列为拍板项或扩展包，避免在负责人未确认前扩大候选边界。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R23 是“推荐文件集”，不是已经冻结的 branch / commit。
  - 确认 R23 没有把扩展审查证据与最小候选主干混为一体。
  - 确认 R23 明确保留了真正冻结前仍需拍板的边界项。
- 剩余风险：
  - R23 只解决“建议冻结哪些文件”，不替代后续 branch/commit/CI 级冻结动作。
  - 当前远端 CI 仍不覆盖当前本地工作树；冻结候选后仍需重新绑定远端 CI。
  - R4 / R5 gate 仍未解除，最小候选文件集不等于可直接发布。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`；`docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`；`docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`

---

### [R22] 候选纳入清单

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`，把当前工作树按 Include / Exclude / Needs decision 三类整理为可执行候选纳入清单。
  - 将 apps/api、apps/web、deploy、tests/e2e、docs/ 与 docs/coordination/ 里的变更拆分为：真实源码/测试/静态资源、明确应排除的日志/快照/过程材料、以及需要负责人拍板的 CI/Helm/Keycloak/证据型文档。
  - 给出两套冻结方案：最小可送审候选（推荐）与完整内部 release dossier，方便后续真正冻结 branch/commit 前先定范围。
- 验证命令：
  - `git -C "xagent" diff --name-only`
  - `git -C "xagent" ls-files --others --exclude-standard`
  - `Get-ChildItem "xagent\apps\web\public" -Recurse -Force`
  - `Get-ChildItem "xagent\apps\web\08_diff_fix" -Recurse -Force`
  - 交叉核对 `README.md`
  - 交叉核对 `docs/coordination/TASK_BOARD.md`
  - 交叉核对 `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
  - 交叉核对 `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
  - 交叉核对 `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
  - 交叉核对 `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
  - `git diff --check -- docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - 已跟踪变更主体集中在 `apps/api`、`apps/web/src`、`deploy`、`tests/e2e`、`README.md` 与核心 docs，符合真实代码/测试/配置候选特征。
  - 未跟踪文件中，`apps/api/*.log`、`apps/web/*.log`、`apps/api/r3-canvas-snapshot.json` 与 `apps/web/08_diff_fix/codex-ui-1to1-audit-20260705.md` 可明确判定为应排除项。
  - `apps/web/public/assets/xiongbao-logo.png` 与 `apps/web/public/assets/xiongbao-mascot.png` 经源码引用关系确认，应视为真实静态资源纳入候选。
  - `.github/workflows/ci.yml`、`deploy/helm/*`、`deploy/keycloak/xagent-realm.json` 以及 R16/R17/R19/R9 等证据型文档已被列为待拍板项，不在未决前被自动当成冻结候选。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R22 只是“候选纳入清单”，不是已冻结候选。
  - 确认 R22 把源码与日志/快照/过程材料清楚分开，没有把运行产物混入候选。
  - 确认 R22 对 CI/Helm/Keycloak/证据型文档只给出建议与拍板点，没有越权代替负责人做最终范围决策。
- 剩余风险：
  - 当前工作树仍未冻结；R22 只是范围建议，后续仍需真正固定 branch / commit。
  - 远端 CI 仍不覆盖当前本地 `HEAD`；只有候选冻结后重跑 CI，R5 才能建立可信绑定。
  - R4 与 R5 的闭环依赖仍存在，R22 不解除这些 gate。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`；`docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`；`docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`

---

### [R21] 候选冻结 + R4/R5 闭环清单

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`，把“候选冻结、R4 演练、R5 审查包”收敛为可执行闭环清单。
  - 基于 `TASK_BOARD`、R16、R17、R18、R19 与当前本地全绿验证结果，区分“本地质量基线已通过”和“可送审 / 可发布候选仍未闭环”的边界。
  - 把三道关键门拆为：候选冻结、R4 目标环境/full-mode 演练、R5 审查包签发，并为每道门列出前置依赖、执行动作、验收产物和禁止越界宣称的边界。
- 验证命令：
  - 交叉核对 `docs/coordination/TASK_BOARD.md`
  - 交叉核对 `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
  - 交叉核对 `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
  - 交叉核对 `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
  - 交叉核对 `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
  - `git diff --check -- docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - 任务板复核：`R4` 仍为 BLOCKED，`R5` 仍为 BLOCKED，`U2` 为 READY，R8/R14/R15/R16/R17/R18/R19 仍在 REVIEW。
  - R16 复核：full-mode 恢复前置清单已覆盖 secret、账号、端口、依赖、LLM 路径与 rehearsal 步骤，但不构成演练完成证据。
  - R17 复核：R5 当前仍只是 source-data 级准备，不能替代最终 PR 审查包。
  - R18 复核：PR #6 / `d59faa3` 的远端 CI 只覆盖旧候选，不覆盖当前本地 `HEAD`。
  - R19 复核：无密交接模板可作为 R4 输入，但不能单独解除 R4/R5 gate。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 R21 的作用是把闭环路径结构化，而不是越权宣称已完成候选冻结、R4 或 R5。
  - 确认 R21 明确区分“本地质量基线全绿”和“正式送审 / 发布候选未闭环”。
  - 确认 R21 没有把 REVIEW 包自动等价为 DONE。
- 剩余风险：
  - 当前工作树仍未冻结，远端 CI 不能直接为当前本地改动背书。
  - R4 仍需环境/发布负责人提供 full-mode secret、账号、依赖和 LLM 路径后实际实跑。
  - R5 仍必须等待候选冻结、R4 证据与关键 REVIEW 验收后才能签发。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`；`docs/coordination/TASK_BOARD.md`；`docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`；`docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`；`docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`；`docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`

---

### [R20] 最终收尾交付审计包

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`，统一汇总最终收尾交付口径、竞品/开源对标结论、本轮新鲜验证结果与正式交付阻断项。
  - 明确当前最准确结论是“主链可运行 + 试点可交付 / 受控私有部署基础成立”，但截至当前候选仍不能宣称“正式商用 GA 已完成”。
  - 初版记录了本轮阶段性负面事实：前端 `lint/typecheck/build` 通过，后端 `ruff` 通过，许可证门禁通过，而当时 `pytest -q` 有 6 条失败，集中在 creative / workflow runtime 的 `delivery` 契约漂移。
  - 后续已完成根因定位与测试契约同步：`tests/test_creative_studio.py`、`tests/test_workflow.py` 断言已更新，当前前端 `lint/typecheck/build`、后端 `ruff/pytest` 与许可证门禁已全部通过。
  - 将竞品/对标报告的最终交付影响收敛为统一叙事：X-Agent 应以“编排内核 + 适配层 + 独有语义”对外表述，而不是“所有底座全自研”。
- 验证命令：
  - `git -C "xagent" status --short --branch`
  - `git -C "xagent" diff --check`
  - `npm --prefix "xagent/apps/web" run lint`
  - `npm --prefix "xagent/apps/web" run typecheck`
  - `npm --prefix "xagent/apps/web" run build`
  - `apps/api/.venv/Scripts/python.exe -m ruff check xagent tests`
  - `apps/api/.venv/Scripts/python.exe -m pytest -q`
  - `apps/api/.venv/Scripts/python.exe scripts/license_check.py`
- 验证结果：
  - 工作树状态：`master...origin/master [ahead 1, behind 2]`，存在大量 tracked / untracked 改动，当前候选尚未冻结。
  - `git diff --check`：仅出现既有 LF/CRLF 工作区提示，未见新的空白符错误中断。
  - 前端验证：`lint` / `typecheck` / `build` 全部通过；Vite 构建最大 JS chunk 为 `294.19 kB / gzip 96.09 kB`。
  - 后端 lint：`ruff check xagent tests` 通过（`All checks passed!`）。
  - 阶段性回归：`pytest -q` 曾失败 6 条，均指向 creative / workflow runtime 的 `delivery` 契约与旧测试断言不一致。
  - 当前后端测试：在同步 `tests/test_creative_studio.py` 与 `tests/test_workflow.py` 后，定向 6 条用例复跑通过，随后全量 `pytest -q` 复跑通过；输出保留 1 条 `opentelemetry` 的 `DeprecationWarning`。
  - 许可证门禁：通过（未发现禁用许可依赖）。
- Reviewer 关注点：
  - 确认 R20 不把 lite/dev 本地证据误写成 full-mode / staging 演练完成。
  - 确认 R20 如实记录了阶段性 6 条失败、根因定位、测试契约同步与当前 `pytest -q` 已复绿的时间顺序，不用旧 CI 或历史通过结果替代当前候选验证。
  - 确认 R20 把竞品/开源对标结论用于收敛交付叙事，而不是把架构方向正确误写成“正式商用已签发”。
- 剩余风险：
  - `R4` 目标环境 / full-mode 演练仍 BLOCKED；`R5` PR 审查包仍不能签发。
  - 当前远端 CI 证据只覆盖旧候选 `d59faa3`，不覆盖当前本地 `HEAD=a98cea09506243ca2b585029c2c5b677f172845c`。
  - 当前工作树仍未冻结，且存在大量 tracked / untracked 改动；即使本地质量基线已通过，也不能直接把当前工作树视为最终发布候选。
- 关联提交 / PR：未提交
- 证据：`docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`；本节验证结果；`OSS_BENCHMARK_AND_REBUILD_PLAN_20260621.md`

---

### [R19] full-mode 凭据/secret 交接模板包

- 交付人：Codex
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`，提供不含真实 secret 的 full-mode 交接模板。
  - 模板覆盖候选绑定、secret/config 字段、full-mode 账号来源、端口与依赖服务、R4 recovery evidence checklist 和 reviewer checklist。
  - 模板明确要求只填写 secret manager path / CI secret name / ticket reference，不允许把真实 secret、`.env`、`.env.rehearsal`、provider key 或密码写入 Git。
  - R19 保留 R16/U2 依赖标签漂移：R16 仍为 REVIEW，U2 为 Claude Code 交付证据；本包不把它们改成 DONE。
- 验证命令：
  - `rg -n "Candidate Binding|Secret And Config Handoff|Full-Mode Account Source|Port And Dependency Handoff|R4 Recovery Evidence Checklist|Reviewer Checklist|XAGENT_SECURITY__JWT_SECRET|LANGFUSE_NEXTAUTH_SECRET|E2E_USERNAME|XAGENT_LLM__" docs\coordination\reports\R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
  - `rg -n "sk-[A-Za-z0-9]|admin/admin|admin12345|ChangeMe|0123456789abcdef|POSTGRES_PASSWORD=xagent|XAGENT_SECURITY__JWT_SECRET=.{8,}|LANGFUSE_NEXTAUTH_SECRET=.{8,}|LANGFUSE_SALT=.{8,}|LANGFUSE_INIT_USER_PASSWORD=.{8,}" docs\coordination\reports\R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
  - `git diff --check -- docs\coordination\TASK_BOARD.md docs\coordination\reports\delivery-report.md docs\coordination\reports\R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- 验证结果：
  - 模板结构扫描：命中候选绑定、secret/config handoff、账号来源、端口依赖、R4 证据清单、reviewer checklist、JWT/Langfuse/E2E/LLM 字段。
  - 危险值扫描：退出码 1 且无输出，未发现 `sk-*`、`admin/admin`、`admin12345`、`ChangeMe`、测试随机串、`POSTGRES_PASSWORD=xagent` 或直接赋值的 secret。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认模板只收集引用和证明字段，不收集真实 secret。
  - 确认 R19 是 R4 恢复输入，不代表 R4 full-mode / staging 演练完成。
  - 确认 R19 未把 R16/U2/R4/R5 改成完成态。
- 剩余风险：
  - 需要环境/发布负责人实际填写模板并提供 secret-store 引用、账号来源、LLM 路径和端口预检结果后，R4 才能恢复实跑。
  - R19 不提供真实 secret、不启动 compose、不执行 smoke/E2E、不解除 R4/R5 gate。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`

---

### [R18] 候选分支与 PR#6 新鲜度审计

- 交付人：Codex
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`，对比当前本地工作树与 draft PR #6 / commit `d59faa3d66fa6848920fec8995e8d9f50ed68437`。
  - 确认 PR #6 仍是自身 head commit 的远端 CI 证据：`backend`、`frontend`、`license-gate`、`promptfoo-eval` 均为 `SUCCESS`。
  - 确认当前本地工作树不是 PR #6 候选：本地 `HEAD=a98cea09506243ca2b585029c2c5b677f172845c`，`master...origin/master [ahead 1, behind 2]`，且存在 54 个 tracked modified files 与 53 个 untracked files。
  - 给出 R5 影响判断：若 R5 要纳入当前本地 R8/R15/R17/R18 等后续证据，必须冻结新候选分支并重新跑远端 CI，不能复用 PR #6 作为当前工作树全绿证据。
- 验证命令：
  - `gh pr view 6 --json number,url,headRefName,headRefOid,baseRefName,state,isDraft,mergeStateStatus,statusCheckRollup`
  - `git rev-parse HEAD`
  - `git status --short --branch`
  - `git merge-base HEAD d59faa3`
  - `git log --oneline --left-right --cherry-pick d59faa3...HEAD`
  - `git diff --name-status d59faa3..HEAD`
  - `git diff --name-status`
  - `git ls-files --others --exclude-standard`
  - `git diff --check -- docs\coordination\TASK_BOARD.md docs\coordination\reports\delivery-report.md docs\coordination\reports\R18_CANDIDATE_FRESHNESS_AUDIT.md`
- 验证结果：
  - `gh pr view 6`：PR #6 为 open draft，headRefOid=`d59faa3d66fa6848920fec8995e8d9f50ed68437`，mergeStateStatus=`CLEAN`，4 个 CI check 全部 `SUCCESS`。
  - 本地候选状态：`HEAD=a98cea09506243ca2b585029c2c5b677f172845c`，`master...origin/master [ahead 1, behind 2]`；merge-base=`da811423be37c870ca904487cd96c53ce64366cd`。
  - 左右提交差异：PR#6 侧包含 `d59faa3`、`0df469b`、`feff648`；本地侧包含 `a98cea0`，说明当前本地 `HEAD` 不是 PR#6 head。
  - 本地工作树差异：54 个 tracked modified files、53 个 untracked files；涉及 `.github`、`apps/api`、`apps/web`、`deploy`、`docs`、`README`、`tests/e2e`。
- Reviewer 关注点：
  - 确认 R18 只给出 candidate freshness 结论，不把新本地工作树宣称为远端 CI 已覆盖。
  - 确认 R18 没有把 R17 REVIEW 改成 DONE；R18 原任务卡依赖标签中的 `R17(DONE)` 已作为漂移风险记录。
  - 确认 R5 只能把 PR #6 作为 `d59faa3` 的证据，若纳入当前工作树则需要新候选和新 CI。
- 剩余风险：
  - R18 不决定当前 54 个 tracked / 53 个 untracked 文件哪些进入发布候选；这需要发布负责人冻结候选范围。
  - R18 不解除 R4/R5/R8/R15/R17 reviewer gate，也不替代 R5 最终 PR 审查包。
- 关联提交 / PR：draft PR #6；候选提交 `d59faa3d66fa6848920fec8995e8d9f50ed68437`
- 证据：本节验证结果；`docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`

---

### [U2] R4 full-mode 环境恢复执行包

- 交付人：Claude Code
- 日期：2026-07-07
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 基于 `reports/R16_FULL_MODE_REHEARSAL_PREP.md`、`docs/RELEASE_RUNBOOK_V1.md`、`docs/ENVIRONMENT_BASELINE_V1.md`、`docs/DEPLOYMENT_RUNBOOK.md` 与 `deploy/compose/.env.example`，将 R4 的“无法演练”阻塞收敛为可执行的恢复执行包。
  - 明确了 R4 恢复执行的责任分工：发布负责人先冻结候选分支/工作树；环境/发布负责人提供 full-mode secret、显式账号和可用 LLM 路径；Claude Code 负责 compose config 校验、依赖拉起、构建、迁移、smoke、Playwright 与日志/回滚证据归档。
  - 明确当前本地候选仍是脏工作树（`master...origin/master [ahead 1, behind 2]`，HEAD=`a98cea09506243ca2b585029c2c5b677f172845c`），因此 U2 只提供恢复路径，不把当前工作树直接宣称为可执行 rehearsal 候选。
- 验证命令：
  - `git -C "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent" rev-parse HEAD`
  - `git -C "D:\AI编程库\项目库\进行中的项目\xiong bao\xagent" status --short --branch`
  - 交叉核对 `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
  - 交叉核对 `docs/RELEASE_RUNBOOK_V1.md`
  - 交叉核对 `docs/ENVIRONMENT_BASELINE_V1.md`
  - 交叉核对 `docs/DEPLOYMENT_RUNBOOK.md`
  - 交叉核对 `deploy/compose/.env.example`
- 验证结果：
  - 当前观测候选 commit：`a98cea09506243ca2b585029c2c5b677f172845c`。
  - 当前分支状态：`## master...origin/master [ahead 1, behind 2]`，且工作树存在大量未提交改动，因此发布负责人仍需先冻结最终 rehearsal candidate。
  - `deploy/compose/.env.rehearsal` 已存在，但文档明确要求在恢复执行前以 `.env.example` 重新生成或显式 diff，避免延续已失败的旧 rehearsal env。
  - U2 已将 R4 恢复步骤收敛为单一路径：冻结候选 -> 生成/重置 `.env.rehearsal` -> 补齐 full-mode secret/账号/LLM -> 端口预检 -> `apps/web/dist` 重建 -> `docker compose ... config --quiet` -> 启动依赖服务 -> 启动应用 -> 采集 Alembic/pg_dump/日志 -> `/health`/`/ready`/首页 smoke -> `creative-smoke`（必要时 `full-flow`）-> 归档证据。
- Reviewer 关注点：
  - 确认 U2 只把 R4 从“泛阻塞”收敛为“可执行恢复步骤”，没有把 `.env.example`、lite/dev 健康检查或本地页面证据写成 full-mode / staging 演练完成。
  - 确认恢复步骤里把 `LANGFUSE_*`、`XAGENT_SECURITY__JWT_SECRET`、显式账号、LLM 路径、端口、compose config、迁移/备份/日志、creative-smoke/full-flow 都列为前置项或执行项。
  - 确认在 freeze 最终候选前，不把当前脏工作树当作 R4 正式演练输入。
- 剩余风险：
  - U2 不提供真实 secret、full-mode 显式账号、真实 LLM 连通性，也不启动 compose / full-mode 栈；R4 仍保持 BLOCKED，直到这些恢复条件全部满足并完成实跑归档。
  - 当前本地候选仍非 clean；若不先冻结候选并绑定远端 CI/分支，后续 R4 证据可能失配。
  - R5 在 R4 未解除阻塞、R8 未完成验收前，仍不能进入可送审/可发布结论。
- 关联提交 / PR：未提交
- 证据：`reports/R16_FULL_MODE_REHEARSAL_PREP.md`；`docs/RELEASE_RUNBOOK_V1.md`；`docs/ENVIRONMENT_BASELINE_V1.md`；`docs/DEPLOYMENT_RUNBOOK.md`；`deploy/compose/.env.example`；本节验证结果

---

### [R17] PR 证据矩阵源数据补齐

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`，按发布检查表分区汇总 DONE/REVIEW 包的证据入口、当前状态、R5 使用提示与剩余风险。
  - 补充 R8/R15/R17 evidence chain closure notes，明确 R17 现在是 REVIEW、R8/R15/R17 均为 reviewer-ready 边界证据，不替代 R5 或发布签字。
  - 明确 R17 只是 R5 PR 审查包的源数据，不直接产出最终 PR 文案、不勾选发布检查表、不宣称正式 GA。
  - `docs/ROADMAP.md` 将 R17 从待领取状态更新为 REVIEW。
  - 2026-07-07 恢复执行复核：补入 R18/R19 作为后续 READY 候选的源数据提示，同时明确它们不是当前 release gate 证据；修正剩余风险列表，显式把 R17 自身列为 REVIEW。
- 验证命令：
  - `rg -n "Checklist Evidence Matrix|Evidence Index For R5|Remaining Risks To Surface In R5|R4 target-environment rehearsal is still BLOCKED|R1 remote CI evidence covers draft PR #6|R17 is source data only" docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md`
  - `rg -n "R17.*状态: REVIEW|R17.*PR 证据矩阵|R5.*PR 审查包|R4.*BLOCKED" docs\coordination\TASK_BOARD.md docs\ROADMAP.md docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md`
  - `2026-07-07 recovery source scan: rg -n "Codex follow-up candidates|R18/R19 are visible as READY|R8/R14/R15/R16/R17 are REVIEW|R17 is source data only" docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md`
  - `2026-07-07 recovery board scan: rg -n "R17.*状态: REVIEW|R18.*状态: READY|R19.*状态: READY|R4.*BLOCKED|R5.*PR 审查包" docs\coordination\TASK_BOARD.md`
  - `2026-07-07 overclaim scan: rg -n "R17 READY|下一张 Codex READY|PR 证据矩阵源数据已完成|PR 审查包已组装完成|目标环境演练已完成|正式商用 GA|正式发布完成|可直接发布|R8/R14/R15/R16 are REVIEW" docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\coordination\reports\R15_EVIDENCE_SYNC.md docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md docs\coordination\reports\delivery-report.md docs\coordination\TASK_BOARD.md README.md docs\ROADMAP.md`
  - `git diff --check -- docs\coordination\TASK_BOARD.md docs\coordination\reports\delivery-report.md docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md docs\ROADMAP.md`
- 验证结果：
  - R17 报告结构扫描：命中 checklist matrix、R5 evidence index、remaining risks、R4/R1/R17 边界声明。
  - 状态扫描：命中 R17 REVIEW、R5 PR 审查包、R4 BLOCKED 口径。
  - 2026-07-07 recovery source scan：命中 R18/R19 follow-up candidates、R8/R14/R15/R16/R17 REVIEW、R17 source-data-only 边界声明。
  - 2026-07-07 recovery board scan：命中 R17 REVIEW、R18/R19 READY、R4 BLOCKED、R5 PR 审查包口径。
  - 2026-07-07 overclaim scan：过滤验证命令、否定句和 R18/R19 后续候选说明后，仅剩 `docs/ROADMAP.md` 的“不可对外表述 / 正式商用 GA”列表项，为正确边界口径。
  - `git diff --check`：退出码 0；仅保留 ROADMAP 的 LF/CRLF 工作区提示。
- Reviewer 关注点：
  - 确认矩阵是 R5 输入源数据，不是最终 PR 描述或发布签字。
  - 确认 R4、R8/R14/R15/R16/R17 REVIEW、R1 候选 CI 与当前工作树差异、R11 audit 风险都被显式保留。
  - 确认 R18/R19 只被列为后续 READY 候选，不被 R17 当作已完成证据或 release gate 通过条件。
- 剩余风险：
  - R17 不解除 R4 阻塞，不替代 R5 总调度 PR 审查包。
  - 若 R5 的候选分支包含 R13-R17 后续本地改动，需要重新确认远端 CI。
  - R18/R19 的依赖标签仍需后续领取者或总调度确认；R17 不把 R16/R17/U2 改成 DONE。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`

---

### [R15] 任务板与交付证据一致性补齐

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R15_EVIDENCE_SYNC.md`，列出 R15 后的任务状态矩阵和证据入口。
  - `docs/coordination/TASK_BOARD.md` 将 R8 从过期的 `IN_PROGRESS` 恢复为 `REVIEW`，因为 R8 delivery-report 与 R8 audit 已明确记录其重新提交 REVIEW；移除已失效的 Codex 等待阻塞记录。
  - `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md` 和 R8 交付节更新 R10/R11/R12/R13/R14/R15/R16/R17 当前状态，删除旧的待领取口径。
  - `docs/ROADMAP.md` 将 R13 修正为 DONE，并补入 R15 REVIEW、R17 REVIEW 口径。
  - 2026-07-07 恢复执行复核：按固定链路补强 R15，修正 R15 矩阵中 R5/U2 的旧状态，记录 R18/R19 依赖标签与当前 REVIEW 状态的漂移，并同步 U-CODEX live handoff。
- 验证命令：
  - `Select-String -Path docs\coordination\TASK_BOARD.md,docs\coordination\reports\delivery-report.md,docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md,docs\ROADMAP.md -Pattern 'R10/R11/R12 READY','R10/R11/R12 是新补','R8\].*IN_PROGRESS','U-CODEX-20260706-2153','R13 \| REVIEW','未把 R1 写成远端 CI 已全绿' | Where-Object { $_.Line -notmatch 'Select-String|旧状态残留扫描' }`
  - `rg -n "R8.*状态: REVIEW|R15.*状态: REVIEW|R17.*状态: REVIEW|R13.*状态: DONE|R14.*状态: REVIEW|R16.*状态: REVIEW|R4.*目标环境演练" docs\coordination\TASK_BOARD.md`
  - `rg -n "R1|R2|R3|R6|R7|R8|R9|R10|R11|R12|R13|R14|R15|R16|R17|COMMERCIAL_STATUS_SOURCE_OF_TRUTH|当前发布|历史验收口径|不可对外表述" README.md docs\ROADMAP.md docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - `2026-07-07 recovery drift scan: rg -n "U2 \| READY|当前已无可领取的 Codex READY 包|R18.*R17\(DONE\)|R5 \| READY \| TASK_BOARD; still gated by R4 and R8 review|R8/R14/R15/R16 are REVIEW" docs\coordination\reports\R15_EVIDENCE_SYNC.md docs\coordination\TASK_BOARD.md docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md docs\coordination\reports\delivery-report.md`
  - `git diff --check -- docs\coordination\TASK_BOARD.md docs\coordination\reports\delivery-report.md docs\coordination\reports\R15_EVIDENCE_SYNC.md docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\ROADMAP.md`
- 验证结果：
  - 旧状态残留扫描：过滤验证命令自匹配后无输出，表示未发现目标旧口径。
  - 任务板状态扫描：命中 R8 REVIEW、R15 REVIEW、R17 REVIEW、R13 DONE、R14 REVIEW、R16 REVIEW、R4 BLOCKED 口径。
  - 发布口径扫描：命中 SOT、ROADMAP、R8 audit 中的当前状态与“不可对外表述”约束。
  - 2026-07-07 recovery drift scan：复核前命中 R15 矩阵旧 R5/U2 状态、U-CODEX 旧 no-ready 口径、R18/R19 依赖标签漂移和 R17 矩阵遗漏；R15 已修正自身矩阵并把 R18/R19 依赖漂移列为后续领取前需确认的风险。
  - `git diff --check`：退出码 0；仅保留 ROADMAP 的 LF/CRLF 工作区提示。
- Reviewer 关注点：
  - 确认 R8 从 `IN_PROGRESS` 移到 `REVIEW` 是基于已有 R8 交付证据和审计记录，不是重新验收 R8。
  - 确认 R15 只做协调文档 / 证据链同步，没有把 R4、R5、R14、R16、R17 或正式 GA 写成完成。
  - 确认 R17 已作为 PR 证据矩阵源数据提交 REVIEW，且没有被误写成 R5 最终 PR 审查包。
  - 确认 R18/R19 仍只是后续 Codex READY 候选，依赖标签漂移已经暴露，未在 R15 内越权 claim 或转状态。
- 剩余风险：
  - R15 不替代总调度对 R8/R14/R16/R15 的 REVIEW 验收。
  - R4 目标环境演练仍 BLOCKED；R5 PR 审查包仍不应在 R4/R8/R17 未闭环前签发。
  - R18/R19 的依赖标签需要总调度或领取者在后续包中确认；R15 仅记录漂移，不把 R16/R17/U2 误改成 DONE。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R15_EVIDENCE_SYNC.md`

---

### [R16] full-mode 演练前置条件补齐包

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`，把 R4 已知阻塞拆成 secret、账号、端口、依赖服务、LLM 路径、compose/full-mode 入口和恢复步骤。
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 增加 R16 前置清单入口，但保持目标环境演练复选框未勾选。
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 补充 R16 事实：前置清单已形成，但不等于 R4 演练完成。
  - `docs/ROADMAP.md` 将 R16 标为 REVIEW，并保留 R4/R5/R8/R15/R17 等后续闭环项。
- 验证命令：
  - `docker compose --env-file .env.example config --quiet`
  - 设置 R16 演练占位 `XAGENT_SECURITY__JWT_SECRET`、`LANGFUSE_NEXTAUTH_SECRET`、`LANGFUSE_SALT`、`LANGFUSE_INIT_USER_PASSWORD` 后，复跑 `docker compose --env-file .env.example config --quiet`
  - `Get-NetTCPConnection -LocalPort 5432,6379,6333,6334,3001,4000,8080,8081 -ErrorAction SilentlyContinue`
  - `rg -n "R16|LANGFUSE_NEXTAUTH_SECRET|full-mode|E2E_USERNAME|不启动 compose|不等于 R4" docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/ROADMAP.md`
  - `git diff --check -- docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md docs/coordination/reports/delivery-report.md docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/ROADMAP.md docs/coordination/TASK_BOARD.md`
- 验证结果：
  - 缺 secret config：退出码 1，报 `required variable LANGFUSE_NEXTAUTH_SECRET is missing a value`。
  - 补齐 R16 演练占位 secret 后 config：退出码 0。
  - full-stack 依赖端口扫描：退出码 1 且无输出，表示当前未监听。
  - R16 关键口径扫描：命中报告、发布检查表、唯一事实源与 ROADMAP。
  - `git diff --check`：退出码 0，仅有既有 LF/CRLF 工作区提示。
- Reviewer 关注点：
  - 确认 R16 只补 R4 可恢复前置清单和预检证据，没有执行或宣称完成目标环境演练。
  - 确认清单覆盖 `LANGFUSE_*`、`XAGENT_SECURITY__JWT_SECRET`、full-mode 显式账号、端口、依赖服务、LLM 路径和 compose config。
  - 确认 `admin/admin` 仍被限定为 lite/dev，不作为 full-mode 验收账号。
- 剩余风险：
  - R4 仍需实际拉起 compose/full-mode 或目标环境，执行迁移、健康检查、登录、Run Console、E2E/smoke，并归档日志/截图/异常处置。
  - R16 使用演练占位 secret 仅验证 config 渲染，不代表真实 secret manager 或生产凭据已就绪。
  - R5 PR 审查包仍应等待 R4/R8 等依赖闭环后再签发。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`

---

### [R14] Vite chunk warning 根因定位与最小拆包建议

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - `apps/web/src/App.tsx` 将登录后页面改为路由级 `React.lazy` / `Suspense` 加载，保留 `LoginPage` 同步加载。
  - `/creative/canvas` 独立入口与常规 `AppShell` 路由均包裹 `Suspense`，避免 canvas / React Flow 依赖提前进入首屏主包。
  - 新增 `docs/coordination/reports/R14_VITE_CHUNK_SPLIT.md`，记录根因、构建产物、验证结果和边界。
  - 同步更新唯一事实源、发布检查表和 ROADMAP 的 R14 口径。
- 验证命令：
  - `npm run lint`
  - `npm run typecheck`
  - `node --test tests/chatStream.test.mjs`
  - `npm run build`
  - `E2E_BASE_URL=http://127.0.0.1:3100 E2E_USERNAME=admin E2E_PASSWORD=admin npx playwright test specs/full-flow.spec.ts --project=chromium`
- 验证结果：
  - `npm run lint`：退出码 0。
  - `npm run typecheck`：退出码 0。
  - `node --test tests/chatStream.test.mjs`：3 passed。
  - `npm run build`：退出码 0；Vite chunk warning 未出现；最大 JS chunk 为 `assets/index-C1uREjI3.js` 294.19 kB / gzip 96.09 kB。
  - `dist/assets` 复查：最大 JS 文件为 `index-C1uREjI3.js` 288.94 KB，其次为 `style-DNRkz53j.js` 143.06 KB、`CreativeStudioPage-LD-5IVNL.js` 79.46 KB。
  - 本地 API 8000 + Web 3100 下完整 `full-flow.spec.ts`：9 passed。
- Reviewer 关注点：
  - 确认 R14 通过路由级拆包处理 warning，没有提高 `chunkSizeWarningLimit` 或升级 Vite major 来掩盖问题。
  - 确认 `/creative/canvas`、Run Console、设置页、Chat 等关键路由在懒加载后仍由 full-flow 覆盖。
  - 确认本包只清除 Vite chunk warning，不替代 R4 目标环境演练、R5 PR 审查包或全量性能签字。
- 剩余风险：
  - 全量 `npm audit` 的 Vite / esbuild dev-build 工具链风险仍按 R11 结论处理，R14 未做依赖升级。
  - build warning 清零不等于真实生产首屏性能、缓存策略或压测通过。
  - R4 目标环境演练与 R5 PR 审查包仍需由对应任务闭环。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R14_VITE_CHUNK_SPLIT.md`

---

### [R13] Chat SSE 完成态 / 回退闭环修复并复绿 full-flow

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `apps/web/src/api/chatStream.ts`，将 SSE 解析、`done` 完成态和无 `done` 结束的失败判定抽成可测试 helper。
  - `apps/web/src/pages/ChatPage.tsx` 改为通过 `readAgentRunStream` 读取流；无 `done` 时触发既有 `/agents/run` fallback；fallback 成功后清空 SSE error。
  - 修复 Chat 主区渲染条件，`runId` 已存在但没有 `streamText/run/error` 时仍显示“查看运行详情”。
  - 新增 `apps/web/tests/chatStream.test.mjs` 覆盖正常 `done`、缺失 `done` 触发失败、done-only SSE run 仍显示运行详情入口。
  - 新增 `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md` 记录诊断、验证和边界。
- 验证命令：
  - `node --test tests/chatStream.test.mjs`
  - `npm run lint`
  - `npm run typecheck`
  - `npm run build`
  - `E2E_BASE_URL=http://127.0.0.1:3100 E2E_USERNAME=admin E2E_PASSWORD=admin npx playwright test specs/full-flow.spec.ts --project=chromium -g "对话运行 agent"`
  - `E2E_BASE_URL=http://127.0.0.1:3100 E2E_USERNAME=admin E2E_PASSWORD=admin npx playwright test specs/full-flow.spec.ts --project=chromium`
- 验证结果：
  - `node --test tests/chatStream.test.mjs`：3 passed。
  - `npm run lint`：退出码 0。
  - `npm run typecheck`：退出码 0。
  - `npm run build`：退出码 0；仍有既有 Vite chunk warning，JS bundle 606.82 kB / gzip 189.30 kB。
  - `对话运行 agent` 单例：1 passed。
  - 完整 `full-flow.spec.ts`：9 passed。
- Reviewer 关注点：
  - 确认 R13 只修 Chat SSE 完成态 / fallback / runId 主区渲染，不把 R14 chunk warning 或 R4 目标环境演练并入本包。
  - 确认 `readAgentRunStream` 对无 `done` 的流结束显式抛错，从而不会再静默吞掉 fallback。
  - 确认 full-flow 9/9 是本地 API 8000 + 当前仓库 Web 3100 证据，不替代目标环境验收。
- 剩余风险：
  - R14 仍需处理 Vite chunk warning 根因定位与拆包建议。
  - R4 目标环境演练与 R5 PR 审查包仍未由本包闭环。
  - 正式商用发布仍需总调度 gate，不因 R13 单包通过而成立。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`

---

### [R12] SQLite/Alembic 漂移诊断与复验指南

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`，记录当前迁移图、fresh SQLite 复验、旧 `xagent.db` 漂移复现、影响范围和处置建议。
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 补充 R12 事实：当前 head 为 `0005`，旧本地 `apps/api/xagent.db` 为未知 `0007` 且缺 `evidence_records`。
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 在发布与回滚章节增加 R12 迁移风险提示，但不勾选目标环境演练项。
  - `docs/ROADMAP.md` 将 R12 调整为 REVIEW 口径。
- 验证命令：
  - SQLite 结构检查脚本：检查 `apps/api/xagent.db` 与 `apps/api/r3-e2e.db` 的 `alembic_version`、表清单和 `evidence_records` 是否存在。
  - fresh DB：`XAGENT_DB__URL=sqlite+aiosqlite:///./r12-fresh.db` 后执行 `alembic current`、`alembic upgrade head`、`alembic current`。
  - 漂移复现：创建仅含 `alembic_version=0007` 的 `r12-drift-0007.db` 后执行 `alembic current` 与 `alembic upgrade head`。
  - 迁移图：`alembic heads` 与 `alembic history --verbose`。
  - 旧默认库：`XAGENT_DB__URL=sqlite+aiosqlite:///./xagent.db` 后执行 `alembic current` 与 `alembic upgrade head`。
- 验证结果：
  - 当前迁移图：`0005 (head)`；history 仅包含 `0001 initial schema` 与 `0005 unified run spine`。
  - fresh `r12-fresh.db`：迁移执行 `base -> 0001 -> 0005`，`alembic_version=0005`，存在 `evidence_records`。
  - R3 fresh `r3-e2e.db`：`alembic_version=0005`，存在 `evidence_records`。
  - 旧 `apps/api/xagent.db`：`alembic_version=0007`，缺 `evidence_records`；`alembic current` / `upgrade head` 均报 `Can't locate revision identified by '0007'`。
  - 伪造 `r12-drift-0007.db`：稳定复现同一 `Can't locate revision identified by '0007'`。
  - R12 临时复现库已清理。
- Reviewer 关注点：
  - 确认 R12 判断为历史本地 SQLite 文件漂移，不是 fresh DB 迁移失败。
  - 确认未直接修改迁移脚本或对旧 `xagent.db` 做 `stamp head` 之类掩盖操作。
  - 目标环境若发现非 `0005` 当前 head，必须先备份并单独形成迁移方案。
- 剩余风险：
  - 旧 `apps/api/xagent.db` 仍保留 `0007` 漂移状态；本包只诊断和给出复验/处置指南，不迁移历史数据。
  - 需要保留历史 SQLite 数据时，必须另拆一次性数据升级任务。
  - R12 不替代 R4 目标环境迁移演练和发布证据归档。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`

---

### [R11] npm audit 与前端构建风险处置包

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/coordination/reports/R11_NPM_AUDIT_FRONTEND_BUILD_RISK.md`，拆解全量 `npm audit`、`npm audit --omit=dev`、Vite/esbuild 依赖树、Vite chunk warning 的真实影响。
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 补充 R11 风险事实：生产依赖 audit 为 0，全量 dev-build 工具链仍有 1 moderate / 1 high。
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 增加 R11 证据入口，但不勾选正式发布项。
  - `docs/ROADMAP.md` 将 R11 调整为 REVIEW 口径，并保留 R12 / R1 / R4 / R5 未闭环。
- 验证命令：
  - `npm audit --json`
  - `npm audit --omit=dev --json`
  - `npm run build`
  - `npm ls vite esbuild --all`
  - `npm outdated vite esbuild --long`
- 验证结果：
  - `npm audit --json`：exit=1；metadata 为 1 moderate / 1 high / total 2。
  - `npm audit --omit=dev --json`：exit=0；metadata 为 0 vulnerabilities。
  - `npm run build`：exit=0；产物生成成功；JS bundle 606.20 kB / gzip 189.09 kB；Vite chunk warning 仍存在但不改变退出码。
  - `npm ls vite esbuild --all`：`vite@5.4.21`，`esbuild@0.21.5`。
  - `npm outdated vite esbuild --long`：`vite` latest 为 `8.1.3`，直接依赖 wanted 仍为 `5.4.21`；`esbuild` latest 为 `0.28.1`。
- Reviewer 关注点：
  - 确认 R11 没有把全量 npm audit 风险写成已清零；只是区分生产依赖面和 dev/build 工具链面。
  - 确认未通过提高 Vite chunk 阈值掩盖 warning，也未在本包内做 Vite semver-major 升级。
  - 若本次交付要求全量 `npm audit` 为 0，需要另拆 Vite major 升级包并重新验证前端构建 / E2E。
- 剩余风险：
  - 全量 `npm audit` 仍不为 0；Vite/esbuild dev-build 工具链风险需发布负责人接受或后续升级处理。
  - chunk warning 仍是性能 / 拆包风险，不阻断 build gate，但应进入 PR reviewer 关注点。
  - R11 不替代 R1 远端 CI、R4 目标环境演练、R5 PR 审查包或 R10 full-flow 剩余 Chat SSE 修复。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R11_NPM_AUDIT_FRONTEND_BUILD_RISK.md`

---

### [R10] full-flow E2E 补齐与差异归因

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 修正 `tests/e2e/specs/full-flow.spec.ts` 中已漂移的 Playwright selector：主导航 link、设置页 heading、短剧 brief textbox、生成画布按钮、React Flow wrapper / 节点断言、对话运行图标按钮。
  - 新增 `docs/coordination/reports/R10_FULL_FLOW_E2E_TRIAGE.md`，记录 full-flow 复验结果、剩余失败归因、影响范围与后续修复清单。
  - 未修改 Chat 运行时代码；对话 SSE 完成态问题作为 R10 边界外后续修复项，不把失败伪装成通过。
- 验证命令：
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "首页加载"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "设置页索引库"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "智能体角色列表"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "后台任务可进入"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "短剧工厂生成草稿"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "设置页加载"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "响应含安全头"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "工作流创建执行"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium --grep-invert "对话运行 agent"`
  - `npx playwright test specs/full-flow.spec.ts --project=chromium -g "对话运行 agent"`
- 验证结果：
  - 首页加载、设置页索引库、智能体角色列表、后台任务 Run Console、短剧工厂、设置页加载、安全头、工作流创建执行单例均通过。
  - 排除 `对话运行 agent` 后 full-flow：`8 passed`。
  - `对话运行 agent` 未通过：登录成功，`POST /api/v1/stream/agents/run` 返回 200，但 100s 内主页面未出现“查看运行详情”；失败快照停留在用户消息与输入区，已清理 Playwright 残留进程。
- Reviewer 关注点：
  - 确认 R10 只修复 E2E selector 漂移并提交结构化归因，没有跨包修改 Chat 运行时代码。
  - 确认不能把 R10 解释为 full-flow 全量通过；当前证据是 8/9 通过，1 条 Chat SSE 完成态阻断。
  - 关注后续是否需要拆新任务修复 `/api/v1/stream/agents/run` 无 done 事件时的前端 fallback 或后端 done 事件保证。
- 剩余风险：
  - `tests/e2e/specs/full-flow.spec.ts` 全量仍不能宣称绿；PR / 发布门禁需要在 Chat SSE 修复后重新跑完整 full-flow。
  - R10 本地 API/Web 证据不替代 R1 远端 CI、R4 目标环境演练或 R5 PR 审查包。
- 关联提交 / PR：未提交
- 证据：本节验证结果；`docs/coordination/reports/R10_FULL_FLOW_E2E_TRIAGE.md`

---

### [R9] 关键页面截图/验收记录补齐

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `tests/e2e/specs/r9-visual-evidence.spec.ts`，用 Playwright 采集登录、对话/工作台、工作流、Run Console、设置页索引库截图。
  - 新增 `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`，记录截图目录、页面验收点、执行命令、结果和剩余边界。
  - 生成 5 张截图到 `docs/coordination/reports/evidence/r9-key-pages/`。
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 增加 R9 本地页面证据引用，但保持发布签字复选框未勾选。
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 补入关键页面本地截图 / 验收记录事实，并明确目标环境页面验收仍需 R4 或发布负责人签字。
- 验证命令：
  - 启动本地 API：设置 `XAGENT_DB__URL=sqlite+aiosqlite:///./r9-visual-evidence.db` 后运行 `apps/api/.venv/Scripts/xagent.exe serve --host 127.0.0.1 --port 8000`
  - 启动本地 Web：`npm run dev -- --host 127.0.0.1 --port 3100`，`XAGENT_DEV_API_TARGET=http://127.0.0.1:8000`
  - `E2E_BASE_URL=http://127.0.0.1:3100 npx playwright test specs/r9-visual-evidence.spec.ts --project=chromium`
  - PNG 存在性与字节数检查
  - PNG 尺寸检查（System.Drawing）
  - `rg -n "R9_KEY_PAGE_VISUAL_EVIDENCE|r9-key-pages|关键页面" ...`
  - `git diff --check -- tests/e2e/specs/r9-visual-evidence.spec.ts docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/coordination/TASK_BOARD.md docs/coordination/reports/delivery-report.md`
  - trailing whitespace scan
- 验证结果：
  - Playwright：`1 passed`
  - 截图文件：`01-login.png`、`02-chat-workbench.png`、`03-workflow.png`、`04-run-console.png`、`05-settings-index.png` 全部存在且非空。
  - 尺寸检查：5 张 PNG 均为 `1440x1000`。
  - R9 证据引用扫描：检查表、唯一事实源、R9 验收记录和任务板均能定位证据入口。
  - `git diff --check`：退出码 0。
  - 尾随空白扫描：退出码 0 且无输出。
- Reviewer 关注点：
  - 验证 R9 只补关键页面截图 / 验收记录，没有宣称目标环境演练完成。
  - 验证发布检查表未提前勾选，只补了证据引用。
  - 验证截图覆盖的页面与任务卡边界一致：登录、对话/工作台、工作流、Run Console、设置页。
- 剩余风险：
  - 本包为本地 dev API/Web 页面证据，不替代 R1 远端 CI、R4 目标环境演练或 R5 PR 审查包。
  - 不覆盖长任务模型质量、性能、压测或真实生产 secret 注入。
- 关联提交 / PR：未提交
- 证据：本节验证结果、`docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md` 与 `docs/coordination/reports/evidence/r9-key-pages/`

---

### [R8] 对外口径一致性终检包

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - `README.md` 新增 2026-07-06 当前状态口径，并把 Phase 0-5 改为历史阶段与当前收口项。
  - `docs/ROADMAP.md` 重写为历史功能阶段、当前 readiness 收口、PR 审查前最低条件、后续增强和不可对外表述。
  - `docs/项目总览与开发指南.md` 明确自身为功能版图与历史开发入口，历史“全部完成 / 商用交付 / 生产就绪”不等同当前正式 GA。
  - `docs/XIONG_BAO_接手与启动说明_2026-07-03.md` 增加 2026-07-06 覆盖说明，限定 `admin/admin` 仅为 lite/dev 本地验证口径，并同步 R2/R3/R6/R7 证据现状。
  - 新增 `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md`，记录差异清单、未完成项和验证命令；`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 补入 R8 审计记录链接。
  - 2026-07-06 二次刷新：同步 R2/R3/R6/R7/R9 DONE、R8 重新提交 REVIEW，并记录当时 R10/R11/R12 后续风险收口包已补单。
  - 2026-07-06 R15/R17 刷新：同步 R1/R2/R3/R6/R7/R9/R10/R11/R12/R13 DONE、R8 REVIEW、R14/R15/R16/R17 REVIEW 的最新任务板状态。
  - 2026-07-07 恢复执行复核：按 R8 -> R15 -> R17 顺序先刷新 R8 可验收证据；R8 仍保持 REVIEW，不替代 reviewer 验收。
- 验证命令：
  - `rg -n "Phase 0.*（当前）|项目唯一权威入口|全项目完成 ✅ \\+ 商用化推进 ✅|默认账号仍可登录|当前已验证可用的默认账号|需要尽快做一次\\*\\*类型检查|下一步最值得|R8 对外口径一致性终检。" README.md docs\ROADMAP.md docs\项目总览与开发指南.md docs\XIONG_BAO_接手与启动说明_2026-07-03.md`
  - `rg -n "R1|R2|R3|R6|R7|R8|R9|R10|R11|R12|R13|R14|R15|R16|R17|COMMERCIAL_STATUS_SOURCE_OF_TRUTH|当前发布|历史验收口径|不可对外表述" README.md docs\ROADMAP.md docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - `$scan = rg -n "R17 READY|下一张 Codex READY|PR 证据矩阵源数据已完成|PR 审查包已组装完成|目标环境演练已完成" docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\coordination\reports\R15_EVIDENCE_SYNC.md docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md docs\coordination\reports\delivery-report.md docs\coordination\TASK_BOARD.md; $scan | Where-Object { $_ -notmatch 'rg -n|未把|当前 READY|不再残留' }`
  - `2026-07-07 recovery stale scan: $scan = rg -n "R17 READY|下一张 Codex READY|PR 证据矩阵源数据已完成|PR 审查包已组装完成|目标环境演练已完成|正式商用 GA|正式发布完成|可直接发布" docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\coordination\reports\R15_EVIDENCE_SYNC.md docs\coordination\reports\R17_PR_EVIDENCE_MATRIX_SOURCE.md docs\coordination\reports\delivery-report.md docs\coordination\TASK_BOARD.md README.md docs\ROADMAP.md; $scan | Where-Object { $_ -notmatch 'rg -n|未把|不再残留|不得宣称|不构成|不作为|不等同|Not formal GA|尚未达到正式商用 GA' }`
  - `git diff --check -- README.md docs\ROADMAP.md docs\项目总览与开发指南.md docs\XIONG_BAO_接手与启动说明_2026-07-03.md docs\RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md docs\COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs\coordination\TASK_BOARD.md docs\coordination\reports\delivery-report.md docs\coordination\reports\R15_EVIDENCE_SYNC.md`
  - `Select-String -Path ... -Pattern "[ \t]+$"`
- 验证结果：
  - 旧口径残留扫描：退出码 1 且无输出，表示未发现目标旧措辞。
  - R8 / SOT / 任务状态关联扫描：命中 ROADMAP 与 R8 审计记录中的 R1/R2/R3/R6/R7/R9/R10/R11/R12/R13 DONE、R8 REVIEW、R14/R15/R16/R17 REVIEW 口径，以及 SOT 的 R8 审计链接。
  - stale R17 claimable-state / overclaim 扫描：过滤验证命令自匹配后无输出，表示 R8/R15/R17 证据链不再把 R17 写成待领取状态，也未把 R4/R5 写成完成。
  - 2026-07-07 recovery stale scan：过滤验证命令、否定句和边界声明后无输出；README 命中的“尚未达到正式商用 GA”为正确否定口径。
  - `git diff --check`：退出码 0；仅输出 README / ROADMAP / 项目总览的 CRLF 工作区提示。
  - 尾随空白扫描：退出码 0 且无输出。
- Reviewer 关注点：
  - 验证 R8 只处理对外口径一致性，没有把 R4/R5/R14/R15/R16/R17 写成已完成或已验收。
  - 验证 README / ROADMAP / 项目总览 / 接手说明均能指回唯一事实源。
  - 验证历史完成态仍可追溯，但不再作为当前正式 GA 结论。
  - 验证 2026-07-07 恢复执行只补强 R8 可验收证据，没有抢 R4/R5 或把 R8 改成 DONE。
- 剩余风险：
  - 本包不提供目标环境演练、PR 审查包、待审包验收或 PR 证据矩阵；这些仍分别由 R4/R5/R14/R15/R16/R17 闭环。
  - 下一步应继续按固定链路刷新 R15 状态/证据一致性，再刷新 R17 PR 证据矩阵源数据。
- 关联提交 / PR：未提交
- 证据：本节验证结果与 `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md`

---

### [U1] 为 R1 生成远端 CI 决策与解阻包

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 汇总本地工作树、远端 PR / CI、任务板与发布门禁现状，形成 R1 恢复所需的远端 CI 决策包。
  - 明确当前本地 `master` 不是可直接推送候选：`ahead 1 / behind 2`、共有 75 条脏状态记录（其中 25 条为未跟踪），且 `.github/workflows/ci.yml` 也在本地改动集合中。
  - 形成 3 个决策选项，并推荐“隔离 readiness 候选分支后推送并通过 PR / workflow_dispatch 触发远端 CI，同时退休 PR #2、将 PR #4 视为非 readiness 阻断”。
- 验证命令：
  - `git fetch origin`
  - `git branch --show-current`
  - `git rev-list --left-right --count master...origin/master`
  - `git status --porcelain`
  - `git worktree list`
  - `gh auth status`
  - `gh pr view 2 --json ...`
  - `gh pr view 4 --json ...`
  - `gh pr view 5 --json ...`
  - `gh run list --limit 8 --json ...`
  - 读取 `.github/workflows/ci.yml`
- 验证结果：
  - 本地主工作树：`master`，相对 `origin/master` 为 `ahead 1 / behind 2`；当前共有 75 条 `git status --porcelain` 记录，其中 25 条为未跟踪文件；不能把它当成可直接推送的 readiness 候选。
  - 现有本地隔离工作树存在：`.claude/worktrees/commercial-readiness`；远端不存在对应 `origin/*readiness*` 分支。
  - CI 触发条件已确认：`push` 仅针对 `main/master/develop`，任意 `pull_request` 会触发，且支持 `workflow_dispatch`；jobs 包含 `backend` / `frontend` / `license-gate` / `promptfoo-eval`。
  - 已知远端绿色记录仅覆盖旧状态：`origin/master@0df469b` 的 push CI success；PR #5 `frontend-preview-boundaries@2ad1bb4` 全绿。
  - PR #4 当前 `UNSTABLE`，backend failed；PR #2 当前 `DIRTY` 且无有效 status rollup；当前没有任何远端 CI run 覆盖本地 `master@a98cea0` 或未提交状态。
  - 推荐选项：授权基于隔离 readiness worktree 准备干净候选、推送远端并通过 PR 到 `master` 或 `workflow_dispatch` 触发 CI；同时退休 PR #2，将 PR #4 作为单独非 readiness 阻断流处理。
- Reviewer 关注点：
  - 确认 U1 只产出决策与解阻包，没有把旧绿色 CI 误写成当前 readiness 候选已全绿。
  - 确认推荐选项明确禁止直接推送当前脏的本地 `master`。
  - 确认 PR #2 / PR #4 的处置建议足以让 R1 恢复，而不把 R4/R5 误并入同一决策。
- 剩余风险：
  - run `28789809193` 仍在执行中，R1 尚不能标记 DONE；必须等待 backend / promptfoo-eval 等检查完成并确认结论。
  - branch protection 未能通过 GitHub API 校验（403），后续 merge gating 仍需以仓库实际策略为准。
  - 即便 R1 远端 CI 最终全绿，正式商用发布仍需 R4 环境演练、R5 PR 审查包，以及 R8/R10/R11/R12 等剩余证据闭环。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [R2] frontend build 可复现验证与构建门禁补齐

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - `.github/workflows/ci.yml` 的 `frontend` job 在 `npm run typecheck` 后新增 `npm run build`，补齐前端构建门禁。
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 同步最小 CI 基线，明确 frontend build 已纳入 CI，关键 Playwright E2E 与当前工作树远端 CI 绿色记录仍需补齐。
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 同步前端 lint/typecheck/build 已本地通过、CI 已补入前端静态 / 构建门禁的真实状态。
  - 未修改 ESLint、TypeScript、Vite 构建阈值或依赖版本。
- 验证命令：
  - `npm ci`
  - `npm run lint`
  - `npm run typecheck`
  - `npm run build`
  - `git diff --check -- .github/workflows/ci.yml docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/coordination/TASK_BOARD.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - `npm ci`：退出码 0，按 `package-lock.json` 重装 293 packages；输出仍提示 1 moderate / 1 high npm audit vulnerability，未在本包内升级依赖。
  - `npm run lint`：退出码 0，`eslint .` 无错误。
  - `npm run typecheck`：退出码 0，`tsc -b --noEmit` 通过。
  - `npm run build`：退出码 0，`tsc -b && vite build` 通过；产物 `index.html`、CSS、JS bundle 生成成功；Vite 输出 chunk size warning（JS 606.20 kB / gzip 189.09 kB），不阻断构建。
  - `git diff --check`：退出码 0；`.github/workflows/ci.yml` 有 Git 的 LF/CRLF 工作区提示，但无 whitespace error。
- Reviewer 关注点：
  - 确认 R2 只补 frontend build 本地证据与 CI build gate，没有把远端 CI 或 Playwright E2E 伪装成已完成。
  - 确认发布检查表复选框仍保持发布负责人对具体版本 / 环境的签字语义，未被提前勾选。
- 剩余风险：
  - 当前工作树仍没有对应的远端 CI 绿色记录，R1 仍需通过 U1 解阻后恢复。
  - npm audit 仍提示 1 moderate / 1 high vulnerability；本包未扩展到依赖升级或安全审计。
  - Vite chunk size warning 仍存在，属于性能/拆包优化风险，不阻断本次 build gate。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [R3] 关键 E2E 冒烟包补齐并跑通

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - `tests/e2e/specs/creative-smoke.spec.ts` 增加登录页真实登录冒烟，并把 canvas 冒烟对齐当前 `/creative/canvas` 页面、`短剧 brief` 标签与 Run Console 可见结果。
  - 修复 canvas run 后 `/runs/{workflow_run_id}` 读取 404：`apps/api/xagent/api/v1/canvas.py` 在运行成功后持久化 workflow view。
  - `apps/api/tests/test_creative_studio.py` 增加最小回归测试，覆盖创建画布、运行画布、再读取 Run Console runtime 详情。
- 验证命令：
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m ruff check apps/api/xagent/api/v1/canvas.py apps/api/tests/test_creative_studio.py`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_creative_studio.py::test_canvas_run_persists_workflow_for_run_console`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_e2e_drama_canvas.py`
  - `npm ci`（工作目录：`tests/e2e`）
  - fresh local DB：`apps/api/r3-e2e.db`，设置 `XAGENT_MODE=lite`、`XAGENT_DB__URL=sqlite+aiosqlite:///./r3-e2e.db`、`XAGENT_CANVAS_SNAPSHOT=r3-canvas-snapshot.json` 后执行 `xagent.cli migrate`
  - `Invoke-RestMethod http://127.0.0.1:8000/api/v1/auth/login` 与 `http://127.0.0.1:3100/api/v1/auth/login`，验证 `admin/admin` 经 API 与 Vite proxy 均可登录
  - `E2E_BASE_URL=http://127.0.0.1:3100 npx playwright test specs/creative-smoke.spec.ts --project=chromium`
- 验证结果：
  - Ruff：`All checks passed!`
  - 新增 canvas run 回归测试：`. [100%]`
  - 既有 `tests/test_e2e_drama_canvas.py`：`. [100%]`
  - `tests/e2e npm ci`：新增 3 个包，0 vulnerabilities。
  - fresh SQLite 迁移：退出码 0，执行 `initial schema` 与 `unified run spine` 升级。
  - API `/health`：200 OK；`admin/admin` 通过 8000 直连与 3100 proxy 均返回 bearer token。
  - Playwright `creative-smoke.spec.ts`：4 passed，覆盖登录、Creative Studio canvas run -> Run Console、canvas batch media task polling、Creative Run Console recovery panel。
  - 审计说明：曾有一轮 Playwright 在 8000 服务不健康时失败；该轮未作为通过/失败证据，已在确认 `/health` 与登录均正常后复跑同一命令并通过。
- Reviewer 关注点：
  - 确认 canvas run 只补 workflow view 持久化，没有扩展到工作流 runtime 任务模型重构。
  - 确认 Playwright 冒烟覆盖的是关键路径证据，不等同完整 full-flow 发布验收。
  - 确认 R3 依赖 R2 的前端 build 仍处于 REVIEW，若 R2 被退回需同步复核本包。
- 剩余风险：
  - 当前工作树远端 CI 仍未闭环，R1 仍为 BLOCKED。
  - 本地默认 SQLite 曾存在旧 alembic revision `0007` 漂移；R3 证据使用 fresh `r3-e2e.db` 复现，不修复用户既有本地库。
  - 未运行 `tests/e2e/specs/full-flow.spec.ts`，该全量流仍应由后续发布验收或 R4/R5 证据包处理。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [R6] 发布/回滚 Runbook v1 补齐

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/RELEASE_RUNBOOK_V1.md`，覆盖发布输入、发布前 gate、构建与配置校验、数据备份、DB 迁移、Compose 发布、发布后 smoke、回滚步骤、异常处置入口与证据归档模板。
  - `docs/DEPLOYMENT_RUNBOOK.md` 增加指向 release runbook 的入口说明，保留原部署形态说明。
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 同步事实口径：Runbook v1 已补齐，但目标环境完整演练仍需 R4 完成。
- 验证命令：
  - `Test-Path docs/RELEASE_RUNBOOK_V1.md`
  - `rg -n "发布步骤|DB 迁移|回滚步骤|发布后 Smoke|异常处置入口|证据归档" docs/RELEASE_RUNBOOK_V1.md`
  - `rg -n "RELEASE_RUNBOOK_V1" docs/DEPLOYMENT_RUNBOOK.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/RELEASE_RUNBOOK_V1.md`
  - `git diff --check -- docs/DEPLOYMENT_RUNBOOK.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - PowerShell trailing whitespace 扫描：`docs/RELEASE_RUNBOOK_V1.md`、`docs/DEPLOYMENT_RUNBOOK.md`、`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`、任务板、交付报告
- 验证结果：
  - `docs/RELEASE_RUNBOOK_V1.md` 存在。
  - 关键章节命中：DB 迁移、发布步骤、发布后 Smoke、回滚步骤、异常处置入口、证据归档模板。
  - `RELEASE_RUNBOOK_V1` 引用存在于发布检查表、部署 Runbook、唯一事实源和新 Runbook；发布检查表仍保持未勾选状态。
  - `git diff --check`：退出码 0，仅有 LF/CRLF 工作区提示。
  - trailing whitespace 扫描：无输出。
- Reviewer 关注点：
  - 确认 R6 只补发布/回滚 runbook 与入口引用，没有把目标环境演练写成已完成。
  - 确认 full / prod 不允许默认 `admin/admin` 的口径在 runbook 中保持清晰。
  - 确认回滚步骤对 DB 恢复、服务回退和 smoke 复验有可执行入口。
- 剩余风险：
  - 未执行真实 compose 发布或回滚演练；该证据属于 R4。
  - 远端 CI 当前由 R1 独立处理中，R6 不提供 CI 全绿结论。
  - K8s / HA / 蓝绿发布仍明确不在 v1 覆盖范围。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [R7] 环境基线与 secret 注入说明补齐

- 交付人：Codex
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 新增 `docs/ENVIRONMENT_BASELINE_V1.md`，明确 dev / staging / prod 环境分层、配置基线、secret 清单、compose / Helm 注入方式、危险默认值禁用策略、发布前环境验收与剩余缺口。
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 环境章节补充环境基线文档入口，但复选框保持未勾选。
  - `docs/RELEASE_RUNBOOK_V1.md`、`docs/DEPLOYMENT_RUNBOOK.md` 与 `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 同步引用环境基线，并明确真实目标环境 secret manager / secretRef 接入仍需 R4 或平台化任务演练。
- 验证命令：
  - `Settings.validate_for_production()`：full 模式下分别验证弱配置失败、强配置通过
  - `docker compose --env-file .env.example config --quiet`：缺 secret 场景与提供强 secret 场景
  - `helm template xagent deploy/helm`：缺 `security.jwtSecret` 场景与提供强 secret 场景
  - `Test-Path docs/ENVIRONMENT_BASELINE_V1.md`
  - `rg -n "环境分层|配置基线|Secret 清单|注入方式|危险默认值禁用策略|发布前环境验收|剩余缺口" docs/ENVIRONMENT_BASELINE_V1.md`
  - `rg -n "ENVIRONMENT_BASELINE_V1" docs/DEPLOYMENT_RUNBOOK.md docs/RELEASE_RUNBOOK_V1.md docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 验证结果：
  - 弱 full 配置返回问题：CORS `*`、JWT secret 少于 32 字符、`require_auth=False`。
  - 强 full 配置返回 `[]`。
  - compose 缺 secret：退出码 1，报 `required variable LANGFUSE_NEXTAUTH_SECRET is missing a value`。
  - compose 提供强 secret：退出码 0。
  - Helm 缺 `security.jwtSecret`：退出码 1，报 `security.jwtSecret is required...`。
  - Helm 提供强 secret：退出码 0，API / worker 模板均渲染 `XAGENT_SECURITY__JWT_SECRET`。
  - 环境基线文档存在；关键章节全部命中。
  - 环境基线入口已出现在部署 Runbook、Release Runbook、发布检查表与唯一事实源。
- Reviewer 关注点：
  - 确认 R7 把 secretRef / secret manager 标为目标环境演练或平台化任务，不伪装为当前 Helm v1 已完整支持。
  - 确认 `admin/admin` 仅限 lite/dev 的口径清晰，full / prod 不接受默认账号作为证据。
  - 确认发布检查表仍未被提前勾选。
- 剩余风险：
  - 未执行真实目标环境 secret manager / K8s secretRef 接入；该证据属于 R4 或平台化任务。
  - `POSTGRES_PASSWORD=xagent` 仍作为本地 compose 示例值存在，文档已要求 staging / prod 覆盖为强密码或托管 DB 凭据。
  - 远端 CI 全绿仍由 R1 继续闭环。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [R4] 目标环境演练与发布证据归档

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 基于 `RELEASE_RUNBOOK_V1`、`ENVIRONMENT_BASELINE_V1` 与当前本机运行态，审计 R4 是否能执行目标环境或 staging 等价演练。
  - 复核了当前 live stack（127.0.0.1:8000 / 127.0.0.1:3000）与 compose/full-mode 前置条件，确认当前只能提供 lite/dev 级别证明，无法构成 full/staging 等价发布演练。
  - 将阻塞条件结构化为可恢复项：缺 Langfuse 必填 secrets、缺 full-mode 显式账号、compose 依赖端口未起、未形成 full-mode 可用 LLM 路径演练证据。
- 验证命令：
  - `curl.exe -f http://127.0.0.1:8000/health`
  - `curl.exe -f http://127.0.0.1:8000/ready`
  - `curl.exe -f http://127.0.0.1:3000`
  - `docker compose --env-file .env config --quiet`
  - `docker compose --env-file .env.rehearsal config --quiet`
  - 检查端口：5432/6379/6333/6334/3001/4000/8080/8081
  - `npx playwright test specs/r9-visual-evidence.spec.ts --project=chromium`
  - 读取 `apps/api/api-8000.log`
- 验证结果：
  - 当前 live stack 可访问：`/health` 返回 `{"status":"ok","version":"0.1.0"}`；`/ready` 返回 `ready=true`；`http://127.0.0.1:3000` 返回 200。
  - `apps/api/api-8000.log` 明确当前运行模式为 `lite`，且日志中存在 `default_admin=true` 记录；这只能作为 lite/dev 证据，不能作为 full/staging 发布演练证据。
  - `deploy/compose/.env` 与 `.env.rehearsal` 虽存在，但 `docker compose ... config --quiet` 对两者均失败，报缺少 `LANGFUSE_NEXTAUTH_SECRET`（同类还包括 `LANGFUSE_SALT`、`LANGFUSE_INIT_USER_PASSWORD`）。
  - compose 依赖服务端口 5432/6379/6333/6334/3001/4000/8080/8081 当前均未监听，因此不存在可直接复用的 full-stack 运行面。
  - 尝试复用 R9 页面截图 spec 作为最小 UI smoke 时失败：`specs/r9-visual-evidence.spec.ts` 在当前 3000 页面上找不到标题 `熊宝智能体系统`，说明现有本地页面证据脚本不能直接作为 R4 full/staging 等价演练替代项。
- Reviewer 关注点：
  - 确认 R4 没有把 lite/dev 健康检查或本地页面可达性误写成 full/staging 发布演练完成。
  - 确认阻塞条件已经具体到可恢复的 secret、凭据、依赖服务与演练入口，不是泛泛而谈的“环境未就绪”。
  - 确认 R5 仍应等待 R4 真正闭环后再做最终 PR 审查包签发。
- 剩余风险：
  - 当前只能做 lite/dev 级别证明，不能满足发布门禁中“目标环境或 staging 等价演练”的 R4 验收要求。
  - 需要补齐 `LANGFUSE_NEXTAUTH_SECRET` / `LANGFUSE_SALT` / `LANGFUSE_INIT_USER_PASSWORD`、full-mode 显式账号、至少一条 full-mode LLM 路径，并拉起 compose 依赖服务后，才能执行真实 rehearsal。
  - R4 未闭环前，R5 不应给出可送审/可发布级别结论。
- 关联提交 / PR：未提交
- 证据：本节验证结果、`docs/RELEASE_RUNBOOK_V1.md`、`docs/ENVIRONMENT_BASELINE_V1.md`、`apps/api/api-8000.log`

---

### [R1] 远端 CI 全绿收口与失败项清零

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 按任务板领取 R1 后，采集 GitHub Actions、开放 PR、远端分支与本地工作树状态。
  - 通过 U1 解阻后，新建 fresh worktree `worktree-r1-remote-ci`，基于 `origin/master` 整理 readiness 候选，并以提交 `d59faa3` 推送远端。
  - 已创建 draft PR #6（`worktree-r1-remote-ci -> master`）并触发当前 readiness 候选的远端 CI；run `28789809193` 已完成并全绿。
- 验证命令：
  - `gh auth status`
  - `gh run list --limit 10 --json databaseId,workflowName,headBranch,headSha,status,conclusion,createdAt,updatedAt,event,url`
  - `gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,headRefOid,mergeCommit,updatedAt,url,statusCheckRollup`
  - `gh run view 28713509646 --json ...`
  - `gh run view 28600088083 --json ...`
  - `gh run view 28645322618 --json ...`
  - `gh run view 28645322618 --job 84950461413 --log-failed`
  - `gh pr checks 4; gh pr checks 5`
  - `gh api repos/xiongpinji/xiongbao/branches/master/protection`
  - `python -S -m ruff check xagent tests`
  - `npm run lint`
  - `npm run typecheck`
  - `git push -u origin worktree-r1-remote-ci`
  - `gh pr create --draft`
  - `gh pr view 6 --json ...`
  - `gh pr checks 6`
  - `gh run view 28789809193 --json status,conclusion,jobs,url`
- 验证结果：
  - `gh auth status`：已登录 `xiongpinji`，具备 `repo` / `workflow` scopes。
  - 本地主工作树：`master`，相对 `origin/master` 为 `ahead 1 / behind 2`；当前共有 75 条 `git status --porcelain` 记录，其中 25 条为未跟踪文件；不能把它当成可直接推送的 readiness 候选。
  - 现有本地隔离工作树存在：`.claude/worktrees/commercial-readiness`；远端不存在对应 `origin/*readiness*` 分支。
  - CI 触发条件已确认：`push` 仅针对 `main/master/develop`，任意 `pull_request` 会触发，且支持 `workflow_dispatch`；jobs 包含 `backend` / `frontend` / `license-gate` / `promptfoo-eval`。
  - 已知远端绿色记录仅覆盖旧状态：`origin/master@0df469b` 的 push CI success；PR #5 `frontend-preview-boundaries@2ad1bb4` 全绿。
  - PR #4 当前 `UNSTABLE`，backend failed；PR #2 当前 `DIRTY` 且无有效 status rollup；当前没有任何远端 CI run 覆盖原本地 `master@a98cea0` 或未提交状态。
  - fresh 候选分支 `worktree-r1-remote-ci` 已推送到 `origin/worktree-r1-remote-ci`，HEAD=`d59faa3d66fa6848920fec8995e8d9f50ed68437`。
  - draft PR #6 已创建：`https://github.com/xiongpinji/xiongbao/pull/6`。
  - 远端 CI run `28789809193`（event=`pull_request`，head=`worktree-r1-remote-ci` / `d59faa3`）已完成，整体结论 `success`。
  - PR #6 当前 checks：`backend` pass、`frontend` pass、`license-gate` pass、`promptfoo-eval` pass。
- Reviewer 关注点：
  - 不要把 2026-07-04 PR #5 的绿色 CI 解释为当前本地 readiness 工作树已远端全绿。
  - 需要确认 PR #4 / PR #2 是继续修复、关闭为过期 PR，还是由 owner 指定合并策略。
  - 需要明确 R1 只闭环远端 CI，不把 R4/R5/R8/R10/R11/R12 等后续发布证据包误写成已完成。
- 剩余风险：
  - 远端候选 CI 已全绿，但 R1 仍只覆盖“远端 CI 收口”；正式商用发布仍需 R4 环境演练、R5 PR 审查包，以及 R8/R10/R11/R12 等剩余证据闭环。
  - branch protection 未能通过 GitHub API 校验（403），后续 merge gating 仍需以仓库实际策略为准。
- 关联提交 / PR：候选提交 `d59faa3`; draft PR #6
- 证据：本节验证结果、PR #6、run `28789809193`

---

### [P0-E] CI 最小门禁与真实状态文档对齐

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - `.github/workflows/ci.yml` 新增 `frontend` job，使用 Node 20、`npm ci`、`npm run lint`、`npm run typecheck` 作为前端最小静态门禁。
  - 保留后端 CI 既有 `ruff check xagent tests` 与 `pytest -q` 门禁，不降低后端 CI 强度。
  - `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 更新到 2026-07-06 真实状态，区分本轮 readiness 本地收口证据与正式 GA 所需远端 CI / 环境演练。
  - `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 增加 2026-07-06 预检口径与最小 CI 基线说明，保留发布签字复选框不提前勾选。
  - 跨包最小修复 `apps/api/tests/test_workflow.py` 中当前后端 CI 阻断：修正新增测试的 lint 问题、审批 step id 路由数据与 delivery bundle 断言。
- 验证命令：
  - `python -S -m ruff check xagent tests`
  - `.\\apps\\api\\.venv\\Scripts\\python.exe -X utf8 -m pytest -q apps\\api\\tests\\test_workflow.py::test_workflow_delivery_summary_exposes_structured_failure_bundle_for_cancelled_run`
  - `python -S -m pytest -q tests/test_system.py tests/test_security_middleware.py tests/test_adapters.py tests/test_orchestration.py tests/test_e2e_drama_canvas.py`
  - `npm run lint`
  - `npm run typecheck`
  - `git diff --check -- .github/workflows/ci.yml docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md apps/api/tests/test_workflow.py docs/coordination/TASK_BOARD.md docs/coordination/reports/delivery-report.md`
  - `python -m alembic upgrade head`（裸本机 Python 复现环境问题）
  - `python -S -m alembic upgrade head`（隔离方式验证迁移本身）
- 验证结果：
  - Ruff 全仓后端门禁：`All checks passed!`
  - 新增 workflow 失败 bundle 测试：`. [100%]`
  - 已知稳定后端集合：`......................... [100%]`
  - `npm run lint`：退出码 0，`eslint .` 无错误。
  - `npm run typecheck`：退出码 0，`tsc -b --noEmit` 通过。
  - `git diff --check`：退出码 0。
  - 裸 `python -m alembic upgrade head`：失败于本机全局 site 读取中文路径 `.pth` 的 `UnicodeDecodeError: gbk`。
  - `python -S -m alembic upgrade head`：迁移执行通过，说明上述失败是本机解释器环境噪音，不是迁移脚本本身失败。
- Reviewer 关注点：
  - CI 只新增前端最小静态门禁，没有把 `frontend build` 或 Playwright 伪装成已纳入最小 CI。
  - 后端 CI 既有 `pytest -q` 保留；本机全量 pytest 未作为通过证据。
  - 发布检查表复选框仍保持发布负责人对具体版本 / 环境的签字语义。
- 剩余风险：
  - 本机全量 `python -S -m pytest -q` 因测试 fixture 子进程改用裸 `python -m alembic`，仍会触发本机全局 `.pth` 的 GBK 解码失败；`.venv` 全量 pytest 运行 304 秒超时，未形成全量通过证据。
  - 尚未产生远端 GitHub Actions 绿色记录；正式发布仍必须补远端 CI、frontend build、关键 Playwright E2E 与环境演练记录。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [P0-C] preview/demo 污染清理

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - `apps/web/src/pages/AgentsPage.tsx` 正式路径不再使用 `fallbackRoles`，接口不可用时不展示本地预览角色。
  - `apps/web/src/pages/WorkflowsPage.tsx` 默认工作流名从 demo 改为正式空白工作流语义，默认步骤不再携带“打招呼 / 你好”示例目标。
  - 未新增 demo fallback，也未调整后端接口合同。
- 验证命令：
  - `rg -n -F -e 'fallbackRoles' -e '本地预览角色' -e 'UI 演示' -e 'useState("demo")' -e '打招呼' -e 'goal: "你好"' -e '默认 demo workflow' -e 'demo workflow' apps/web/src/pages apps/web/src/components apps/web/src/api`
  - `npm run lint`
  - `npm run typecheck`
  - `git diff --check -- apps/web/src/pages/AgentsPage.tsx apps/web/src/pages/WorkflowsPage.tsx docs/coordination/TASK_BOARD.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - preview/demo 关键模式复扫：退出码 1 且无输出，表示无匹配。
  - `npm run lint`：退出码 0，`eslint .` 无错误。
  - `npm run typecheck`：退出码 0，`tsc -b --noEmit` 通过。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认正式页面没有继续依赖 `fallbackRoles` 或本地预览提示。
  - 确认工作流默认值不再把 demo 示例伪装成正式能力。
  - 同文件存在既有 UI 改动，本包只验收 demo/fallback 清理边界。
- 剩余风险：
  - 本包不处理页面既有交互/视觉改动的产品验收。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [P0-B] 前端 lint 阻断

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 在 `apps/web/tests/runConsoleViews.test.mjs` 和 `apps/web/tests/runtimeApi.test.mjs` 显式导入 `URL` from `node:url`。
  - 未修改 ESLint 全局配置，未降低 lint 规则强度。
- 验证命令：
  - `npm run lint`
  - `node --test tests/runConsoleViews.test.mjs tests/runtimeApi.test.mjs`
  - `git diff --check -- apps/web/tests/runConsoleViews.test.mjs apps/web/tests/runtimeApi.test.mjs docs/coordination/TASK_BOARD.md docs/coordination/reports/delivery-report.md`
- 验证结果：
  - `npm run lint`：退出码 0，`eslint .` 无错误。
  - `node --test ...`：能启动测试，8 pass / 4 fail；失败点为既有合同漂移（shell action 解构断言、`delivery.failure: null` 默认字段），不属于 P0-B lint 阻断。
  - `git diff --check`：退出码 0。
- Reviewer 关注点：
  - 确认 P0-B 只修复 Node 测试文件 `URL` 全局 lint 错误。
  - 确认没有修改 ESLint 配置或降低规则强度。
- 剩余风险：
  - Node 测试合同漂移仍存在，应另拆测试/Run Console 合同修复包；本包不扩 scope。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [P0-D] 危险默认值清零

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - `Settings.validate_for_production()` 拒绝空值、旧占位、短 JWT secret；lite 默认 JWT secret 加长到 32+ 字符但仍被 full/enterprise 禁用。
  - `get_user_store()` 仅在 lite 模式 seed `admin/admin`，full/enterprise 不再内置默认管理员。
  - compose 删除 JWT / Langfuse `change-me` / `admin12345` fallback，改为 `.env` 显式必填。
  - Helm `security.jwtSecret` 默认置空，并在 API / worker 模板中用 `required` fail fast。
  - Keycloak realm 不再导入默认 admin 用户，也移除固定 OIDC client secret。
  - README / Runbook / Integration Guide / full E2E 说明同步为显式凭据。
- 验证命令：
  - `python -S -m pytest -q tests/test_settings.py tests/test_enterprise.py tests/test_auth.py tests/test_security_middleware.py`
  - `python -S -m ruff check xagent/infra/settings.py xagent/enterprise/auth/users.py tests/test_settings.py`
  - `docker compose --env-file .env.example config --quiet`
  - 设置 `XAGENT_SECURITY__JWT_SECRET`、`LANGFUSE_NEXTAUTH_SECRET`、`LANGFUSE_SALT`、`LANGFUSE_INIT_USER_PASSWORD` 后运行 `docker compose --env-file .env.example config --quiet`
  - `helm template xagent deploy/helm`
  - `helm template xagent deploy/helm --set api.enabled=true --set security.jwtSecret=0123456789abcdef0123456789abcdef`
  - `Get-Content deploy/keycloak/xagent-realm.json -Raw | ConvertFrom-Json`
  - `rg -F` 复扫 deploy / README / Runbook / Integration Guide / full-flow 中的旧危险默认值
  - `python -S -m pytest -q tests/test_e2e_drama_canvas.py`
  - `PYTHONIOENCODING=utf-8 python -S -c "from xagent.cli import main; raise SystemExit(main(['smoke']))"`
  - `npx playwright test specs/full-flow.spec.ts --list`
- 验证结果：
  - 后端设置 / 认证 / 安全中间件测试：`............................. [100%]`
  - Ruff：`All checks passed!`
  - compose 缺 secret：按预期失败，报 `required variable LANGFUSE_NEXTAUTH_SECRET is missing a value`
  - compose 提供强 secret：退出码 0
  - Helm 缺 `security.jwtSecret`：按预期失败，报 `security.jwtSecret is required...`
  - Helm 提供强 secret 且启用 API：API / worker 均渲染 `XAGENT_SECURITY__JWT_SECRET`
  - Keycloak realm JSON：解析通过
  - 危险默认值复扫：无 `admin12345`、旧 `change-me-*` fallback、`jwtSecret: "change-me"`、Langfuse 弱默认匹配
  - `tests/test_e2e_drama_canvas.py`: `. [100%]`
  - `xagent smoke` 等效 CLI 入口：`[smoke] PASS ✅ 三链路全通`
  - Playwright full-flow 解析：列出 9 个测试，退出码 0
- Reviewer 关注点：
  - full/enterprise 不再 seed `admin/admin` 是否符合当前交付登录初始化方案。
  - compose / Helm 的 fail-fast 是否满足部署团队对 secret 注入方式的预期。
  - Keycloak realm 移除默认用户和固定 client secret 后，部署文档是否足够指导显式初始化。
- 剩余风险：
  - 仍需 P0-E 最终同步发布检查表勾选状态与 CI 门禁；本包只修默认值基线。
  - 裸 `pytest` / Python console script 仍受本机全局中文路径 `.pth` 的 GBK 解码问题影响；本次验证继续使用 `python -S` 隔离入口，未修改全局环境。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

### [P0-A] orchestration await bug

- 交付人：Claude Code
- 日期：2026-07-06
- 关联分支 / 工作树：master / `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 变更摘要：
  - 修复 `apps/api/xagent/core/orchestration/loop.py` 提示工程 tool fallback 分支未 `await _handle_prompt_tool_action(...)` 的 correctness bug。
  - 在 `apps/api/tests/test_orchestration.py` 增加最小回归测试，覆盖 tool action -> tool result -> final 的事件序列，并断言下一轮 LLM 输入已包含工具结果。
- 验证命令：
  - 在仓库根设置 `PYTHONPATH=apps/api`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_orchestration.py`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -c "from xagent.cli import main; raise SystemExit(main(['info']))"`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -c "from xagent.cli import main; raise SystemExit(main(['smoke']))"`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_system.py`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_security_middleware.py`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_adapters.py`
  - `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_e2e_drama_canvas.py`
- 验证结果：
  - `apps/api/tests/test_orchestration.py`: `......... [100%]`
  - `xagent info` 等效 CLI 入口：输出 `mode=lite`、SQLite、in-memory cache、Qdrant memory、Langfuse disabled`，退出码 0。
  - `xagent smoke` 等效 CLI 入口：`[smoke] PASS ✅ 三链路全通`，退出码 0。
  - `apps/api/tests/test_system.py`: `.... [100%]`
  - `apps/api/tests/test_security_middleware.py`: `... [100%]`
  - `apps/api/tests/test_adapters.py`: `........ [100%]`
  - `apps/api/tests/test_e2e_drama_canvas.py`: `. [100%]`
- Reviewer 关注点：
  - `loop.py` 仅补 `await`，没有改动原生 function-calling 分支。
  - 回归测试是否足够覆盖提示工程 fallback 分支的工具结果写回。
- 剩余风险：
  - 本机全局 `_editable_impl_xagent.pth` 指向中文路径 worktree，裸 `pytest` / Python console script 在 site 阶段可能触发 `UnicodeDecodeError: gbk`；本次验证使用仓库内虚拟环境 Python + `-X utf8` + 显式 `PYTHONPATH=apps/api` 绕过该环境噪音，未修改仓库代码以外配置。
  - `apps/api/tests/test_e2e_drama_canvas.py` 仍出现既有 `InsecureKeyLengthWarning`，对应危险默认值属于 P0-D 范围，不在 P0-A 内处理。
- 关联提交 / PR：未提交
- 证据：本节验证结果

---

## 回溯索引

- `P0-A` orchestration await bug
- `P0-B` 前端 lint
- `P0-C` preview/demo 污染清理
- `P0-D` 危险默认值
- `P0-E` CI 最小门禁与真实状态文档对齐
