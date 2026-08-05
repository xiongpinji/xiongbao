# Roadmap v2 A 平台化增强真实验证计划

> 适用阶段：Roadmap v2
>
> 用途：把 A 平台化增强包从“方向定义”推进到“可执行验证”，明确 Helm / K8s / secretRef / external secret manager / 标准环境模板的验证范围、方法与证据要求。

---

## 1. 目标

本计划的目标是：

> **为 `xagent` 的平台化增强路线提供第一份真实验证计划，使 A 包不再停留在概念层，而进入可验证状态。**

---

## 2. 验证范围

本次验证只覆盖以下内容：

1. Helm chart 当前可表达的部署能力；
2. secret 注入当前态与目标态之间的差距；
3. 标准环境模板是否已经具备最小抽象基础；
4. 哪些平台化能力当前已经真实存在，哪些仍只是方向目标。

本次验证**不**要求一次性完成：
- 完整 secretRef 落地；
- 完整 external secret manager 接入；
- 全量 K8s 集群验证；
- 平台化自动部署流水线。

---

## 3. 验证环境

当前优先采用：
- 仓库中已有 Helm 模板与环境基线文档的等价验证环境；
- 用于确认 chart 渲染、secret 注入方式、模板边界与环境模板化能力。

环境前提：
- 可读取 `deploy/helm/values.yaml`；
- 可执行 `helm template`；
- 可读取 `ENVIRONMENT_BASELINE_V1.md`；
- 可引用 `G3-C1` 的验证结果。

---

## 4. 验证项

### 4.1 Helm / K8s 渲染能力

验证：

```powershell
helm template xagent deploy/helm --set api.enabled=true --set security.jwtSecret=<32+ chars random>
```

期望：
- 当前 chart 能成功渲染；
- API / worker / web 的基础结构存在；
- `jwtSecret` 仍保持 fail-fast；
- 不依赖危险默认值才可渲染。

### 4.2 secret 注入当前态与目标态

验证：
- 当前 secret 注入是否仍主要为 env / values；
- 文档中是否已经明确 `secretRef` / external secret manager 是目标态；
- 没有把“未来能力”误写为“当前已完成能力”。

期望：
- 能清楚区分当前态与目标态；
- 能给出后续平台化优先级。

### 4.3 环境模板基础

验证：
- `ENVIRONMENT_BASELINE_V1.md` 是否已清楚区分 dev / staging / prod / enterprise；
- 当前是否已有环境模板最小骨架；
- 是否已经有可以继续抽象的配置边界。

期望：
- 标准环境模板方向已具备材料基础；
- 不是从零开始设想。

---

## 5. 通过标准

A 平台化增强包的真实验证通过，至少需要满足：

1. Helm / K8s 当前能力已被真实确认；
2. secret 注入当前态与目标态差距已明确；
3. 环境模板基础已被明确识别；
4. 可以区分当前已存在的平台化能力与后续真正要补的能力。

这意味着：
- A 包的“通过”不是平台化已经完成；
- 而是平台化路线已经进入真实可执行验证阶段。

---

## 6. 证据要求

本计划要求输出的最小证据包括：

- Helm 渲染结果摘要
- 当前 secret 注入方式说明
- 目标 secret 注入方式说明
- 当前环境模板基础说明
- 最终判定：
  - 通过 / 不通过
  - 哪些已验证
  - 哪些仍是下一步目标

建议归档到：
- `docs/coordination/reports/roadmap-v2-platformization-verification.md`

---

## 7. 当前结论

当前 A 平台化增强包已完成方向定义；
这份计划的作用是让它进入下一状态：

> **可执行验证**

只有完成这一步，`A 平台化增强包` 才能从“方向定义”走向“验证完成”。
