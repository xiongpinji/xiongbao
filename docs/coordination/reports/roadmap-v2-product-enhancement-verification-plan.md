# Roadmap v2 E 产品增强真实验证计划

> 适用阶段：Roadmap v2
>
> 用途：把 E 产品增强包从“方向定义”推进到“可执行验证”，明确 Goal / taskboard 自动推进、review / recover / evidence 自动化增强、工作台体验优化与更细粒度执行/治理视图的验证范围、方法与证据要求。

---

## 1. 目标

本计划的目标是：

> **为 `xagent` 的产品增强路线提供第一份真实验证计划，使 E 包不再停留在方向层，而进入可验证状态。**

---

## 2. 验证范围

本次验证只覆盖以下内容：

1. 当前 Goal / taskboard 自动推进的基础是否已存在；
2. 当前 review / recover / evidence 自动化增强的基础是否已存在；
3. 当前工作台体验增强的关键入口是否已存在；
4. 当前执行 / 治理视图增强的基础是否已存在；
5. 哪些能力已具备真实增强基础，哪些仍是后续目标。

本次验证**不**要求一次性完成：
- 全量 UI 重构；
- 所有自动推进逻辑实现；
- 所有 evidence 自动生成；
- 完整多层治理可视化平台。

---

## 3. 验证环境

当前优先采用：
- 仓库中已有 Goal 结构、Goal Board、Run Console、交付包与验证材料的等价验证环境；
- 用于确认产品增强不是从零开始，而是已有真实入口与已完成基础。

环境前提：
- 能读取 `commercialization-goal-board.md`
- 能读取 `commercialization-final-summary.md`
- 能读取 G1/G2/G3 执行包与验证材料
- 能读取前端 Goal Board / Run Console 相关文档入口

---

## 4. 验证项

### 4.1 Goal / taskboard 自动推进基础

验证当前是否已存在：
- G0/G1/G2/G3 Goal 结构
- Goal Board 文档入口
- 阶段推进 / Gate 评估记录
- 执行包与验证结果的系统化挂接

期望：
- Goal / taskboard 增强不是纯未来愿景，而是已有真实基础。

### 4.2 review / recover / evidence 自动化基础

验证当前是否已存在：
- 稳定性 / 恢复包
- 稳定性演练记录
- 签字 / 证据包
- 最终汇总文档

期望：
- 自动化增强已有结构化输入对象，不再从零定义。

### 4.3 工作台体验增强基础

验证当前是否已存在：
- Goal Board
- Release / Recovery 侧栏
- Run Console
- Chat / Settings / Run detail 入口

期望：
- 后续体验增强建立在真实已存在的产品面上，而不是抽象想象。

### 4.4 执行 / 治理视图增强基础

验证当前是否已存在：
- Goal Board
- Delivery Materials Index
- Final Summary
- Audit / Comparison 报告

期望：
- 已经有多层视图基础，可以继续增强而不是重建。

---

## 5. 通过标准

E 产品增强包的真实验证通过，至少需要满足：

1. Goal / taskboard 自动推进基础已被真实确认；
2. review / recover / evidence 自动化基础已被真实确认；
3. 工作台体验增强基础已被真实确认；
4. 执行 / 治理视图增强基础已被真实确认；
5. 可以明确区分“已有产品基础”与“后续仍需深挖的增强项”。

这意味着：
- E 包的“通过”不是产品增强已经全部完成；
- 而是产品增强已经进入真实可执行验证阶段。

---

## 6. 证据要求

本计划要求输出的最小证据包括：

- Goal / taskboard 自动推进基础确认结果
- review / recover / evidence 自动化基础确认结果
- 工作台体验增强基础确认结果
- 执行 / 治理视图增强基础确认结果
- 最终判定：
  - 通过 / 不通过
  - 哪些已验证
  - 哪些仍是后续目标

建议归档到：
- `docs/coordination/reports/roadmap-v2-product-enhancement-verification.md`

---

## 7. 当前结论

当前 `E 产品增强包` 已完成方向定义；
这份计划的作用是让它进入下一状态：

> **可执行验证**

只有完成这一步，`E 产品增强包` 才能从“方向定义”走向“验证完成”。
