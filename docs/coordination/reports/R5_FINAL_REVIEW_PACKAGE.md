# R5 最终审查包（当前候选）

> 日期：2026-07-08
> 目标：把当前 `candidate/min-send-review-20260707-claude` 的发布审查输入收敛为一份 reviewer 可直接阅读的最终审查包。
> 边界：本包用于**审查与签发判断**，不是自动宣布“正式商用 GA 已完成”。

---

## 1. 当前审查对象

### 候选主线

- 分支：`candidate/min-send-review-20260707-claude`
- 当前分支 HEAD：`db29505fbce3f6bfe056d6e9073d82e6130e8988`
- PR：[#7](https://github.com/xiongpinji/xiongbao/pull/7)
- 当前远端 CI：GitHub Actions `CI` run `28919902142`，状态 `success`

### 重要现实边界

当前仓库**本地工作树**已继续完成一轮 R4/R5 收口，包含：

- `deploy/compose/postgres-init.sh` 的 LF 修正
- `deploy/compose/docker-compose.yml` 中 worker healthcheck 伪失败修正
- `tests/e2e/specs/full-flow.spec.ts` 的 replay/resume 精确断言收紧
- 本轮新增交付材料与 R4/R5 文档包

因此现在可以明确：

> **远端 CI `28919902142` 已覆盖当前最终候选 commit `db29505fbce3f6bfe056d6e9073d82e6130e8988`，本地新增收口改动已经完成冻结、推送并获得新的远端全绿记录。**

---

## 2. 本轮可直接成立的结论

### 2.1 已成立

- 当前代码线已具备主链可运行能力；
- 最小 CI 门禁已在候选分支上存在并已有成功记录；
- 单机 / Docker Compose `full` 模式已在当前机器完成一轮等价环境实跑；
- 交付材料已经成套，reviewer 可找到部署、运维、已知问题、试点边界、升级路径入口；
- 当前适合判定为：
  - **内部试点可交付**
  - **受控私有部署可交付**
  - **可进入最终 reviewer / owner 判断阶段**

### 2.2 当前不能自动成立

- 若目标环境不是当前机器，则客户目标环境演练已自动完成。

---

## 3. 验证矩阵

| 类别 | 结论 | 证据 |
|---|---|---|
| 候选分支 / PR 存在 | 通过 | PR #7；候选分支 `candidate/min-send-review-20260707-claude` |
| 远端 CI（最终候选） | 通过 | GitHub Actions `28919902142` success，对应 commit `db29505fbce3f6bfe056d6e9073d82e6130e8988` |
| frontend build | 通过 | `npm run build`；R20；R31 |
| backend lint/test | 通过 | `ruff` / `pytest -q`；R20 |
| license gate | 通过 | `scripts/license_check.py`；R20 |
| 环境基线 / secret 文档 | 已补齐 | `ENVIRONMENT_BASELINE_V1.md`；R7 |
| 发布 / 回滚 runbook | 已补齐 | `RELEASE_RUNBOOK_V1.md`；R6 |
| 关键页面视觉证据 | 已补齐（本地） | `R9_KEY_PAGE_VISUAL_EVIDENCE.md` |
| R4 full-mode 等价环境实跑 | 通过（当前机器） | `delivery-report.md#r31-当前机器-r4-full-mode-等价环境实跑` |
| `/health` / `/ready` | 通过 | R31；`r4-evidence` |
| `alembic current` | 通过，`0005 (head)` | R31；`alembic-current.txt` |
| `python -m xagent.cli smoke` | 通过 | R31；`api-smoke.txt` |
| `full-flow.spec.ts` | 通过，9/9 | R31；`full-flow-fixed.txt` |
| 管理员部署手册 | 已补齐 | `ADMIN_DEPLOYMENT_MANUAL_V1.md` |
| 运维手册 | 已补齐 | `OPERATIONS_MANUAL_V1.md` |
| 已知问题 / 试点边界 | 已补齐 | `KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md` |
| 联系人与升级路径 | 已补齐（单人交付模式） | `SUPPORT_ESCALATION_PATH_V1.md` |

---

## 4. reviewer 关注点

### 4.1 这次真正被证明了什么

- 当前机器上的单机 `full` 模式等价环境可以真实拉起；
- health / ready / migration / smoke / 登录 / Run Console / full-flow 主链都已经有实跑证据；
- R4 不再停留在“文档存在”，而是已经有**运行证据**。

### 4.2 这次没有偷偷宣称什么

- 没有把 lite/dev 结果冒充 full-mode 结果；
- 没有把客户目标环境与当前机器等同；
- 没有把远端 CI 覆盖范围夸大到当前本地全部改动；
- 没有把“试点可交付”直接说成“正式商用 GA 已完成”。

### 4.3 本轮最小修复点

本轮为了完成 R4 演练，补了两处最小范围问题：

1. `deploy/compose/postgres-init.sh`
   - 修复工作区 CRLF 导致的 `/bin/bash^M`
2. `deploy/compose/docker-compose.yml`
   - 对 worker 禁用继承自 API 镜像的 `/health` 探针，消除 Celery 进程的伪失败

另有一处测试收口：

3. `tests/e2e/specs/full-flow.spec.ts`
   - replay/resume 文本在 UI 上重复出现，原 strict selector 误报；已收紧断言到对应 card 语义范围

---

## 5. 剩余风险

### 5.1 当前真正还剩的技术/流程风险

1. **若目标交付环境不是当前机器**
   - 仍需在目标机器 / 客户现场复演一次。

2. **正式商用签发仍需 owner 明确接受**
   - 尤其是是否将“当前机器的等价环境实跑”作为本次正式交付依据。

3. **当前交付边界仍限定于单机 / Docker Compose `full` 模式**
   - 不自动外推为 K8s / HA / 多机 / 客户现场异构环境已完成同等级验证。

### 5.2 当前已不再构成主链阻断的项

- 最终候选未冻结
- 远端 CI 未覆盖最终候选
- full-mode stack 无法拉起
- `/health` / `/ready` 不通过
- migration 不通过
- smoke 不通过
- full-flow 主链失败

这些在当前机器上都已被证据证明通过。

---

## 6. 建议的发布判定

### 建议 A：内部试点 / 受控私有部署
**建议判定：可以成立**

理由：
- 当前候选主链和当前机器等价环境证据已经足够。

### 建议 B：最终候选进入正式签字判断
**建议判定：可以成立**

理由：
- 本地收口改动已经冻结进最终候选；
- 最终候选 commit `db29505fbce3f6bfe056d6e9073d82e6130e8988` 已获得新的远端 CI 全绿记录 `28919902142`；
- 审查材料和 R4 证据都已齐备。

### 建议 C：正式商用可交付
**建议判定：条件成立，取决于你是否接受以下前提**

前提：
1. 你接受“当前机器的 full-mode 等价环境实跑”作为本次正式交付环境依据；
2. 你接受以单人交付模式承担 TL / QA / DevOps / Owner 角色；
3. 你接受当前交付边界限定于单机 / Docker Compose `full` 模式。

如果以上任一前提不接受，则当前更稳妥的口径仍是：
- **受控交付 / 试点可交付**，而非自动宣称“正式商用 GA 已完成”。

---

## 7. reviewer / owner 最终检查单

在你做最终判断前，只需回答这 3 个问题：

1. 是否把当前机器视作本次正式交付的目标环境或可接受等价环境？
2. 是否接受本轮单人交付模式下由同一 owner 覆盖 TL / QA / DevOps / Owner 角色？
3. 是否接受当前交付范围仍限定于单机 / Compose `full` 模式，而不额外承诺 K8s / HA / 客户现场多机？

若三项都回答“是”，则当前最接近的下一步已不再是继续技术补洞，而是：

> **由你完成最终签字。**

---

## 8. 核心证据入口

- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/coordination/reports/delivery-report.md#r31-当前机器-r4-full-mode-等价环境实跑`
- `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`
- `docs/FORMAL_RELEASE_EXTERNAL_CONDITIONS_V1.md`
- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\compose-ps.txt`
- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\alembic-current.txt`
- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\api-smoke.txt`
- `C:\Users\canqu\.claude\projects\d--AI---------------xiong-bao\r4-evidence\full-flow-fixed.txt`

---

## 9. 本包最终建议

> **当前 `xagent` 已达到“当前机器单机 full-mode 正式交付签字条件已满足”的状态。**
>
> **若你接受当前机器作为目标/等价环境，并接受单人签字模式，则现在已经可以直接做最终签字；不再需要额外的技术补洞或 CI 对齐步骤。**
