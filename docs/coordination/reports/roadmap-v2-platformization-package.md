# Roadmap v2 A 平台化增强包

> 适用阶段：Roadmap v2
>
> 用途：在当前商用交付标准已达成的前提下，把平台化增强方向冻结成一份执行包，为后续 K8s / Helm / secretRef / external secret manager / 标准环境模板建设提供统一入口。

---

## 1. 目标

A 平台化增强包的目标是：

> **把 `xagent` 从“已有可交付部署形态”继续推进到“更标准、更可复制、更平台化的部署与配置形态”。**

这一步不要求立刻完成全部平台化，但必须明确：

- secret 注入如何从 env/value 继续走向 `secretRef` / external secret manager；
- Helm / K8s 的增强应该优先补哪些能力；
- 多环境模板该如何抽象；
- 平台化增强的最小输出物是什么。

---

## 2. 当前已有基础

当前已经具备：

- `deploy/helm/values.yaml` 最小 Helm 入口
- `G3-C1 HA / K8s` 方向包及其首轮验证结果
- `ENVIRONMENT_BASELINE_V1.md` 中的环境与 secret 基线
- `ROADMAP_V2.md` 中的平台化增强方向

当前可直接复用的材料：

- `docs/ROADMAP_V2.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`
- `deploy/helm/values.yaml`
- `docs/coordination/reports/commercialization-g3-c1-ha-k8s-package.md`
- `docs/coordination/reports/commercialization-g3-c1-ha-k8s-verification.md`

---

## 3. 当前缺口

### 3.1 secret 注入平台化缺口
- 当前仍主要是 env / values 注入；
- 需要更明确的 `secretRef` / external secret manager 目标形态；
- 需要更标准的 secret ownership 与注入边界。

### 3.2 Helm 表达能力缺口
- 仍需补更标准的平台部署表达；
- 需要让 chart 更接近长期可维护形态；
- 需要明确哪些能力仍只是入口，不是已完成能力。

### 3.3 环境模板缺口
- 需要一套更稳定的 dev / staging / prod / enterprise 模板；
- 需要减少现场手工拼接环境差异。

---

## 4. 下一步输出物

平台化增强包后续应产出：

- 平台化路线图
- secret 注入目标形态说明
- Helm / K8s 增强清单
- 标准环境模板清单
- 平台化验证包

---

## 5. 当前结论

A 平台化增强包的作用不是立刻完成平台化，而是：

> **把平台化增强正式拉成一条新主线，并给后续真实实现与验证提供统一入口。**
