# Roadmap v2 C 容量与性能增强包

> 适用阶段：Roadmap v2
>
> 用途：在当前商用交付标准已达成的前提下，把容量与性能增强方向冻结成一份执行包，为后续压测基线、多实例一致性实证、队列/缓存/LLM 路径瓶颈治理和容量建议收口提供统一入口。

---

## 1. 目标

C 容量与性能增强包的目标是：

> **把 `xagent` 从“知道容量边界在哪里”继续推进到“有更正式的压测结论、瓶颈认知和扩容建议”的状态。**

这一步不要求立即完成完整性能平台，但必须明确：

- 哪些压测入口已经存在；
- 哪些瓶颈对象必须重点关注；
- 哪些容量建议应该形成正式输出；
- 哪些扩容策略是后续必须验证的。

---

## 2. 当前已有基础

当前已经具备：

- `G3-C4` 容量 / 扩展边界包与其首轮真实验证材料；
- `COMMERCIAL_RELEASE_CHECKLIST_V1.md` 中的性能与容量检查项；
- `OPERATIONS_MANUAL_V1.md` 中的 worker、依赖、warmup、pending 等风险入口；
- `tests/load/locustfile.py` 作为当前真实可执行的负载入口。

当前可直接复用的材料：

- `docs/coordination/reports/commercialization-g3-c4-capacity-boundary-package.md`
- `docs/coordination/reports/commercialization-g3-c4-capacity-verification-plan.md`
- `docs/coordination/reports/commercialization-g3-c4-capacity-verification.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/OPERATIONS_MANUAL_V1.md`
- `tests/load/locustfile.py`

---

## 3. 当前缺口

### 3.1 压测基线缺口
- 仍缺一轮更正式的压测结果沉淀；
- 当前有入口，但结论未被标准化。

### 3.2 瓶颈治理缺口
- API / worker / LLM / Redis / Qdrant 的瓶颈对象虽已列出，但后续仍需要更正式的优先级排序与缓解策略。

### 3.3 扩容建议缺口
- 仍需更清晰的 10 / 50 / 100 并发或等价建议口径；
- 仍需更明确的扩容前置条件与风险点。

---

## 4. 下一步输出物

容量与性能增强包后续应产出：

- 正式压测基线结果
- 瓶颈清单与优先级
- API / worker / LLM / Redis / Qdrant 扩容建议
- 用户规模与限制条件说明
- 容量与性能验证包

---

## 5. 当前结论

C 容量与性能增强包的作用不是立即让系统完成无限扩展，而是：

> **把容量增强正式拉成一条新主线，并给后续真实压测、瓶颈治理与扩容建议提供统一入口。**
