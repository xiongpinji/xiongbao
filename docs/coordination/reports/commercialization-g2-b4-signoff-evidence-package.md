# G2-B4 签字 / 证据包

> 适用阶段：G2 正式商用 GA
>
> 用途：把正式商用 GA 的 reviewer 输入、Owner 签字入口、证据索引与最终结论收敛到一个最小可交接的签字 / 证据包，确保正式 GA 不只是完成发布和回滚，而是有可审阅、可签发、可留档的最终证明材料。

---

## 1. 目标

G2-B4 的目标是：

> **把正式商用 GA 的签字判断、证据入口和最终结论收敛成一个 reviewer / owner 可直接使用的最终包。**

这一步不负责再扩展新功能，也不负责再定义发布流程；它只负责：

- 把当前候选与证据索引起来；
- 把 reviewer 需要看的内容收敛到一个入口；
- 把 TL / QA / DevOps / Owner 的签字判断清晰化；
- 把“是否可以正式商用 GA”从技术事实变成可审查结论。

---

## 2. 当前签字对象

G2-B4 签字对象必须基于 G2-B1 冻结的唯一候选：

- branch / candidate line：`commercialization-ladder`
- commit SHA：`3a1eb28dd50c9357538356dda1d19752b012412c`
- PR：`#11`
- PR 状态：`CLEAN`
- CI 结果：backend / frontend / license-gate / promptfoo-eval 全绿

补充证据入口：

- `docs/coordination/reports/commercialization-g2-b1-candidate-freeze-package.md`
- `docs/coordination/reports/commercialization-g2-b2-target-rehearsal-package.md`
- `docs/coordination/reports/commercialization-g2-b3-release-rollback-package.md`
- `docs/coordination/reports/commercialization-goal-board.md`
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`

---

## 3. 签字前 reviewer 需要看的内容

### 3.1 候选冻结

必须先确认：
- 候选对象是唯一的；
- 候选范围已冻结；
- 交付材料索引一致；
- 当前不是脏工作树交付。

### 3.2 目标环境演练

必须确认：
- G2-B2 的目标环境 / full-mode 演练有明确证据；
- 发布 / 回滚 / smoke / migration 闭环可执行；
- 证据留档入口明确。

### 3.3 发布 / 回滚

必须确认：
- G2-B3 的发布 / 回滚包已收口；
- 失败时知道停在哪里、回滚到哪里、留什么证据；
- 不会把发布环境和试点环境口径混淆。

---

## 4. 签字角色

G2-B4 的签字判断由以下角色构成：

- **TL**：判断技术闭环与范围收口是否成立；
- **QA**：判断验证证据和测试门禁是否完整；
- **DevOps**：判断发布 / 回滚 / 环境门禁是否可执行；
- **Owner**：判断风险是否可接受，是否允许进入正式商用结论。

### 4.1 签字原则

签字不是说“没问题”，而是说：

- 我看过证据；
- 我知道边界；
- 我接受当前发布结论；
- 我确认当前候选可以进入正式商用判断。

---

## 5. 最终证据索引

### 5.1 代码与 CI 证据

- `PR #11`
- `backend` / `frontend` / `license-gate` / `promptfoo-eval` 全绿
- 相关 CI run 链接

### 5.2 目标环境与恢复证据

- `docs/coordination/reports/commercialization-g2-b2-target-rehearsal-package.md`
- `docs/coordination/reports/commercialization-g2-b3-release-rollback-package.md`
- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`

### 5.3 交付材料与状态证据

- `docs/coordination/reports/commercialization-goal-board.md`
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
- `docs/coordination/reports/auto-delivery-phase1-report.md`

---

## 6. 最终结论模板

G2-B4 的最终结论建议固定成以下三档之一：

### 6.1 正式商用 GA 可签发
满足条件：
- 候选冻结清晰；
- 目标环境演练完成；
- 发布 / 回滚闭环完成；
- reviewer 证据完整；
- Owner 风险接受。

### 6.2 可内部试点 / 灰度
满足条件：
- 候选与发布条件成立；
- 但仍有少量非阻断项未完全收口；
- 已明确试点边界。

### 6.3 不可签发
触发条件：
- 候选不唯一；
- 目标环境演练不充分；
- 发布 / 回滚不可执行；
- 关键证据缺失；
- owner 不接受风险。

---

## 7. 完成定义

G2-B4 只有在以下条件同时成立时，才算完成：

- 签字角色与签字口径明确；
- 证据入口完整；
- reviewer 可以独立判断；
- 当前正式商用 GA 的最终结论可以被记录；
- G2-B1、G2-B2、G2-B3 的证据都已纳入签字包。

---

## 8. 当前结论

G2-B4 的作用不是再做一次测试，而是：

> **把正式商用 GA 的最终判断、签字角色和证据入口冻结成一个可以直接给 reviewer / owner 使用的签发包。**

一旦 G2-B4 形成，G2 就具备从“已冻结候选”走向“正式商用判断”所需的最终签字材料。