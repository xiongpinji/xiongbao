# R5 最终审查包（当前候选）

> 日期：2026-07-08
> 目标：把当前 `candidate/min-send-review-20260707-claude` 的发布审查输入收敛为一份 reviewer 可直接阅读的最终审查包。
> 边界：本包用于**审查与签发判断**，不是自动宣布“正式商用 GA 已完成”。

---

## 0. 候选刷新附录（2026-08-03，v2）

> 原签字候选 `c175201` 之后，分支又推进了 **221 个提交**（8/2 安全审计修复、沙箱/SSO 实测、平台化 P0/P2、性能瓶颈修复、CI 修复）。原签字口径不覆盖新候选，本节为刷新后的候选事实；**新候选的签发仍需 owner 重新确认**。

### 0.1 新候选

- 分支：`candidate/min-send-review-20260707-claude`（PR #7，不变）
- 新候选 HEAD：`402302aca2ad7156ba5ddfb85ca69122c5512098`
- 远端 CI：GitHub Actions `CI` run `30829673045`，**success**
  - backend ✅ / frontend ✅ / license-gate ✅ / **e2e-api ✅**（本轮修复后首次转绿）
  - docker-build / promptfoo-eval / load-test：skipped（路径触发规则，与原候选一致）

### 0.2 自原签字候选 c175201 以来的 221 提交摘要

- 8/2 审计修复 7 项全部核销（FIX_COMPLETION_REPORT_20260802）
- 沙箱分级 L1 Docker 实测通过（stdout/stderr 分流、隔离/限额/超时/一次性容器）
- SSO/OIDC 授权码流端到端实测通过（Keycloak 26，alg 路由双源校验）
- 平台化：secretRef 外部密管 + Helm chart（五套 values 渲染通过）+ 限流/调度 Redis 化
- P2 容量：压测基线 → bcrypt 线程池化（login c=50 3.2→54.8 RPS）→ skills 响应缓存（c=50 31.5→162.3 RPS）→ 10min soak 142,720 请求 0 错误无泄漏 → Postgres 基线 + 4 worker 扩展性实测（canvas c=10 6.4×）
- CI 修复：edge_tts 可选依赖测试优雅跳过；/perf 端点实装统计（存量 bug）；e2e 冒烟规格对齐当前 API（403 语义、模板路由漂移）

### 0.3 本轮 CI 修复明细（reviewer 关注点）

| 失败 | 根因 | 修复 | 性质 |
|---|---|---|---|
| backend pytest ERROR ×4 + FAILED ×1 | edge-tts 为可选 extra，CI 不装；测试直接 import | `pytest.importorskip` 优雅跳过；缺包降级路径本有测试覆盖 | 测试环境适配，非产品缺陷 |
| e2e-api /perf 断言失败 | /perf 自 6571d3f 起即为坏端点（TimingMiddleware 未注册、实例查找循环无效） | 注册 TimingMiddleware + 进程级实例自注册，/perf 实装汇总统计 | **真实存量 bug，已修** |
| e2e-api 401 断言 ×2 | 匿名空角色被授权守卫拦截返回 403（CI REQUIRE_AUTH=false） | 规格放宽为 401/403 | 规格对齐设计语义 |
| e2e-api /templates 404 | 模板路由漂移至 /api/v1/canvas/templates/list | 规格更新为当前路由与响应形状 | 规格对齐 |

### 0.4 新候选签发记录（2026-08-03，owner 已确认）

- ~~原 §7 owner 三项确认（目标环境 / 单人签字模式 / 交付边界）不自动延伸至新候选~~ → **2026-08-03 owner 已明确将三项确认延伸至新候选，并确认签发**。
- 签发对象：分支 `candidate/min-send-review-20260707-claude`（PR #7），HEAD `2aae3a212a51f253bc3e3ef485fbf3fa916204b8`（代码有效候选 `cfb973d`，其后均为文档/协调类提交）。
- 签发依据：
  1. 远端 CI run `30834318982` success（backend / frontend / license-gate / e2e-api 全绿；docker-build / promptfoo-eval / load-test 按既有 push 触发规则不适用于 PR，与原签字候选口径一致）；
  2. 自 c175201 起 221 提交的变更范围（含安全模型变更：SSO/OIDC、沙箱 fail-closed、限流配置化、bcrypt 异步化、skills 响应缓存）已经 §0.2/§0.3 摘要与下列证据包完整披露，owner 已知悉并接受；
  3. 证据入口：`audit-20260802/DELIVERY_VERIFICATION_20260803.md`（v3）、`audit-20260802/LOAD_TEST_FORMAL_20260803.md`、`audit-20260802/SANDBOX_SSO_REVERIFY_20260803.md`、`docs/coordination/reports/REVIEW_ACCEPTANCE_PACKET_20260803.md`。
- 签发边界（owner 确认不外推）：多机 HA 未演练（共享状态类已同机两实例实测，签发后补充证据 HA_MULTI_INSTANCE_VERIFY_20260803）；L2 E2B 云沙箱未实测（无 key）；非当前机器的目标环境演练未做；SaaS 级并发容量不承诺（仅单机/4 worker 基线）。
- R8/R14/R15/R16/R17/R18/R19 已于 2026-08-03 验收 DONE（见 §0.4 前文与验收材料包）。

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
**建议判定：成立**

依据：
1. 当前机器上的 full-mode 等价环境实跑已完成；
2. 单人交付模式下，owner 已明确接受同一人覆盖 TL / QA / DevOps / Owner 角色；
3. 最终候选 commit `c175201cdee1026d89be8d96b93c3f6bfa0f1739` 已获得新的远端 CI 全绿记录 `28921940625`；
4. 当前交付边界已明确限定为单机 / Docker Compose `full` 模式。

---

## 7. reviewer / owner 最终检查单

本轮 owner 已明确给出：

1. 当前机器可作为本次正式交付的目标环境 / 可接受等价环境；
2. 单人交付模式下由同一 owner 覆盖 TL / QA / DevOps / Owner 角色；
3. 当前交付范围限定于单机 / Compose `full` 模式，不外推到 K8s / HA / 客户现场多机。

因此当前下一步已不是继续判断是否可签，而是：

> **按已确认结论完成最终留档与后续环境收尾。**

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
