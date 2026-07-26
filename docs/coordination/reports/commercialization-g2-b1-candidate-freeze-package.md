# G2-B1 候选冻结包

> 适用阶段：G2 正式商用 GA
>
> 用途：冻结当前候选版本、候选范围、CI 证据与发布前材料入口，确保从 G1 进入 G2 后，项目不再以“持续变化的工作树”作为交付对象，而是以唯一候选版本作为正式商用收口起点。

---

## 1. 目标

G2-B1 的目标是：

> **把当前 `xagent` 的正式商用候选对象固定下来，避免后续发布、演练、签字、回滚都围绕漂移中的内容展开。**

这一步不是做目标环境演练，也不是做发布签字；它只负责：

- 冻结版本对象；
- 冻结交付范围；
- 冻结 CI / 证据入口；
- 冻结正式商用 GA 的起始候选。

---

## 2. 当前候选冻结对象

当前冻结候选如下：

- branch / candidate line：`commercialization-ladder`（基于 `candidate/min-send-review-20260707-claude`）
- commit SHA：`3a1eb28dd50c9357538356dda1d19752b012412c`
- PR：[#11](https://github.com/xiongpinji/xiongbao/pull/11)
- PR URL：`https://github.com/xiongpinji/xiongbao/pull/11`
- mergeStateStatus：`CLEAN`
- 对应 CI run（PR #11）：
  - `backend` ✅
  - `frontend` ✅
  - `license-gate` ✅
  - `promptfoo-eval` ✅
- 交付材料入口：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 当前真实状态口径：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 已知问题 / 试点边界：`docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`

### 当前说明

在 G2-B1 中，当前候选对象的答案是：

1. 这次 GA 候选对象：`commercialization-ladder @ 3a1eb28`，对应 PR #11；
2. 这次候选范围：Goal 结构、G1 阶段四个执行包、G1 Gate 评估与稳定性恢复演练记录；
3. 这些内容属于正式 GA 收口的起始候选，因为它们把“如何从 G1 进入 G2”冻结成了可交接材料；
4. G2 后续仍未纳入的内容包括：目标环境演练、正式发布 / 回滚闭环、签字 / 证据包以及 G3 的长期运营能力；
5. 当前候选的验证证据来自 PR #11 的全绿 checks 与现有交付材料索引。

---

## 3. 候选冻结输入

冻结候选前必须能提供：

- 当前候选 commit
- 关联 PR
- 远端 CI 全绿证据
- 交付材料索引
- 当前真实状态文档
- 已知问题 / 边界说明

参考文档入口：

- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`
- `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
- `docs/coordination/reports/auto-delivery-phase1-report.md`

---

## 4. 冻结后的最小要求

一旦进入 G2-B1，必须满足：

- 不再把未冻结内容混入候选；
- 不再用脏工作树或未提交改动代表交付对象；
- 不再用旧 CI 或无关 PR 的记录冒充当前候选；
- 发布、回滚、签字都必须指向同一个候选对象。

---

## 5. 当前结论

G2-B1 是正式商用 GA 的第一个执行包，它的作用不是“验证系统能不能跑”，而是：

> **确认接下来所有 G2 工作都围绕同一个正式候选对象展开。**
