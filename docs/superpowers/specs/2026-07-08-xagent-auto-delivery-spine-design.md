# X-Agent Auto-Delivery Spine 设计文档

- 日期：2026-07-08
- 主题：补全对标 Codex / Hermes Agent 差距的完整升级方案（以结果交付为导向）
- 当前主方案：**方案 1 / Auto-Delivery Spine**
- 适用范围：xagent Phase 1 升级设计；验证对象为 xagent 用 xagent 升级 xagent 自己

---

## 1. 背景与问题定义

当前 `xagent` 已完成一轮正式交付收口，能够在**当前机器 / 单机 Docker Compose `full` 模式 / 单人交付模式**下实现：

- 最新候选分支冻结与多轮远端 CI 全绿；
- current-machine full-mode 等价环境 R4 实跑；
- R5 最终审查包、release manifest、最终签字记录块与 PR 审查入口收口。

这说明 xagent 已经不是原型，而是具备当前范围内正式交付能力的工程系统。

但如果对标 Codex / Hermes Agent，当前差距已经不主要体现在“能否跑通主链”，而体现在：

### 对标 Codex 的核心差距

1. 缺少默认的远程 / 隔离执行平面；
2. PR 生命周期不是第一类产品对象；
3. 多环境可复制执行不够产品化；
4. 安全 / 审批更多体现在工程治理，而非产品默认行为。

### 对标 Hermes Agent 的核心差距

1. taskboard 不是主控制面；
2. durable session 不够强；
3. 长任务恢复与跨会话推进体验不足；
4. goal-driven 的长期任务系统还未产品化。

### 相对终局目标的差距

1. 还不是 owner 只看报告的系统；
2. 还没有默认自动 merge / deploy / verify / rollback / archive 的完整主链；
3. 还没有把“交付”本身设计成第一类产品能力。

因此，本次升级不是做若干零散功能，而是：

> 把 xagent 从“可交付的单机代理系统”升级成“以产品经理智能体为中枢、能持续推进并完成真实交付的软件交付操作系统”。

---

## 2. 设计目标

本次完整升级方案的总目标是：

> 让 xagent 具备一条从高层目标输入到生产交付、验证、恢复、归档的完整自动交付主脊柱，并由产品经理智能体默认主导持续推进。

### 2.1 Phase 1 成功标准

Phase 1 不是搭平台骨架，而是必须在 xagent 自己身上证明一条完整闭环：

1. 接收高层 goal；
2. 自动拆解成 initiatives / tasks；
3. 在 taskboard 中形成可执行状态；
4. 在隔离执行环境中完成真实改动；
5. 自动形成 candidate / PR / review package；
6. 自动推进 deploy；
7. 自动执行 verify；
8. 必要时自动进入 recovery / rollback；
9. 自动形成 evidence / archive / signoff record；
10. owner 只看最终报告，而不是手工驱动整条链。

### 2.2 本次设计原则

1. **交付优先于功能**：所有能力都服务于交付主链；
2. **状态优先于过程**：goal/task/release/evidence 必须对象化；
3. **智能体优先于人工编排**：默认持续推进；
4. **主链优先于单点能力**：taskboard、sandbox、PR 都服务于同一 Spine；
5. **先做闭环，再做泛化**：先在 xagent 自己身上证明，再扩展到其他仓库。

---

## 3. 总体方案：Auto-Delivery Spine

主方案采用 **Auto-Delivery Spine**。

### 3.1 定义

系统主脊柱固定为：

**Goal → Plan → Taskboard → Execute → Review → Release → Deploy → Verify → Recover → Archive**

这条链既是产品工作流，也是正式状态机。

### 3.2 为什么选这个方案

相较于单纯做“执行核心 + 规划核心”分离架构，或者仅做自治等级路线图，Auto-Delivery Spine 更符合本次目标：

- 它直接以交付闭环为中心，而不是模块堆叠；
- 它同时能容纳 Codex 型差距（隔离执行、PR 原生闭环、多环境执行）；
- 也同时能容纳 Hermes 型差距（taskboard、durable session、长任务推进）；
- 它更适合定义 owner 只看报告的产品形态。

### 3.3 外部评估框架

为了避免 Spine 变成“看起来全自动、其实不可控”，系统外部仍采用自治等级作为评估框架：

- L0 human-driven, agent-assisted
- L1 agent-driven implementation
- L2 agent-driven review + verification
- L3 staging delivery
- L4 production delivery + recovery
- L5 report-only owner

Phase 1 的目标是：

> 至少在 xagent 自己身上，证明从 L2/L3 走向 L4/L5 的最小完整闭环。

---

## 4. 核心架构

### 4.1 三层结构

Auto-Delivery Spine 内部采用三层结构：

#### A. Planning Layer
负责“理解要做什么”：
- goal intake
- initiative/task decomposition
- taskboard stewardship
- prioritization / blockage reasoning

#### B. Execution Layer
负责“把事情做出来”：
- execution environment selection
- code/config change execution
- test / CI / deploy invocation
- artifact production

#### C. Control & Evidence Layer
负责“让系统可恢复、可治理、可留档”：
- durable session
- event log
- release record
- evidence aggregation
- policy / safety
- signoff record
- archive

### 4.2 第一类对象（必须持久化）

以下对象都必须是系统内的第一类持久对象：

- **Goal**：最高层目标
- **Initiative**：goal 下的阶段主题
- **Task**：最小执行单元
- **Run**：某次 task 的执行实例
- **Review**：正式评审结果
- **Release**：候选 / 发布对象
- **Evidence**：所有验证与交付证据
- **Incident / Recovery**：失败与恢复对象

### 4.3 统一状态主线

这些对象由统一主线串起：

**Goal → Initiative → Task → Run → Review → Release → Evidence → Signoff / Recovery**

这样 PM Agent 才能真正跨会话推进，而不是靠聊天记忆维持假连续性。

---

## 5. PM Agent 设计

PM Agent 是产品经理智能体，不是万能代码 bot。

### 5.1 PM Agent 的定位

它是：
- taskboard owner
- session continuity owner
- orchestration owner
- release progression owner
- reporting owner

它不是：
- 每个低层执行动作的亲自承担者
- 单一大脑式的全能代码 bot

### 5.2 核心职责

PM Agent 负责：
1. goal intake
2. decomposition
3. taskboard stewardship
4. execution delegation
5. review gating
6. release progression
7. deploy / recover decisioning
8. reporting & archive

### 5.3 每轮循环

每轮固定执行：
1. 读取当前状态；
2. 找到最高优先级推进点；
3. 决定动作类型；
4. 执行动作；
5. 写回状态；
6. 输出 owner 摘要。

### 5.4 默认行为风格

- 默认主动推进；
- 把人当 owner，不当操作员；
- 面向结果，不面向命令；
- 状态比聊天更重要。

---

## 6. Phase 1 子项目拆分

Phase 1 固定拆成 6 个子项目：

### 6.1 Goal / Taskboard / Session Core
- 持久化 goal / initiative / task；
- 建立主 taskboard；
- 支持 durable session / resume。

### 6.2 Execution Environment Orchestrator
- 统一 current-machine / isolated execution；
- 每次执行都形成 run 对象与证据；
- 支持 execution template selection。

### 6.3 PR / Review / Release Packaging Core
- branch / candidate / commit / PR 对象化；
- 自动生成 review package；
- 统一关联 CI/docs/evidence。

### 6.4 Deploy / Verify / Recover Core
- 支持 deploy 为正式状态；
- verify 为必经层；
- recovery / rollback 进入状态机。

### 6.5 Control / Policy / Safety Core
- 自动推进边界；
- 风险策略；
- 自动化动作 trace；
- recovery 策略驱动。

### 6.6 Evidence / Archive / Continuous Learning Core
- 自动归档 release 结果；
- 自动回看 pass/fail；
- 经验可反馈下一轮 goal/taskboard。

### 6.7 执行顺序

主顺序：
1. Goal / Taskboard / Session Core
2. Execution Environment Orchestrator
3. PR / Review / Release Packaging Core
4. Deploy / Verify / Recover Core
5. Control / Policy / Safety Core
6. Evidence / Archive / Continuous Learning Core

但 4/5/6 不应完全等 1~3 全部完成后才启动，而是当最小 candidate 形成后并行接入。

---

## 7. 完整工作流

### 7.1 端到端链路

1. **Goal Intake**：输入高层目标，建立 session root；
2. **Planning / Decomposition**：生成 initiative / task graph；
3. **Taskboard Activation**：激活主状态面；
4. **Execution**：在执行环境中生成 run / artifact / logs；
5. **Review**：判断结果能否升级到下一层；
6. **Release Packaging**：形成 candidate / PR / review package；
7. **Deploy**：推进部署；
8. **Verify**：自动做 health/ready/smoke/E2E；
9. **Recover**：失败进入 retry / fix-forward / rollback；
10. **Archive**：形成最终留档与经验反馈。

### 7.2 关键特征

- 每一层都是正式状态；
- 智能体推进的是状态，不只是命令；
- owner 默认只看报告，不做流程工；
- workflow 必须支持 replay / resume / recovery / archive。

---

## 8. 新会话产品经理启动方式

### 8.1 新会话必须是 PM Control Session

新会话不是“重新理解世界”，而是：
- 带着状态进入
- 读取 goal / taskboard / runs / release / evidence / archive
- 判断当前 phase
- 找到唯一最高优先级推进点
- 调执行智能体继续推进

### 8.2 新会话启动输入

启动包包含：
1. **Identity**：PM Agent
2. **Scope**：Phase 1 / Auto-Delivery Spine / xagent 自举升级
3. **State**：goal/taskboard/review/release/evidence/archive
4. **Operating Rules**：默认主动推进，先写状态再执行，owner 只看报告

### 8.3 建议启动提示词

```text
你现在是 xagent 的产品经理智能体（PM Agent），负责主导 Auto-Delivery Spine，而不是只做需求整理或聊天辅助。

你的职责是：
- 接收和维护 goal
- 拆解 initiative / task
- 维护 taskboard
- 判断当前最高优先级推进点
- 调度执行智能体
- 推动 review / release / deploy / verify / recovery
- 组织 evidence / archive / report
- 默认持续推进，owner 只看报告

当前主方案：
- 采用 Auto-Delivery Spine：
  Goal → Plan → Taskboard → Execute → Review → Release → Deploy → Verify → Recover → Archive
- 内部分层：
  Planning Layer / Execution Layer / Control & Evidence Layer
- 第一类对象：
  Goal / Initiative / Task / Run / Review / Release / Evidence / Incident

当前阶段目标：
- 推进 xagent 对标 Codex + Hermes Agent 的差距补全
- 当前 Phase 1 目标是：taskboard + durable session + 自动交付一体化闭环
- 验证对象固定为：xagent 用 xagent 升级 xagent 自己
- 目标不是只做代码代理，而是做可持续自动交付操作系统

你的启动流程必须严格按下面顺序：
1. 读取当前 goal / initiatives / taskboard / active runs / review / release / evidence / archive 状态
2. 判断当前所处 phase（planning / execution / review / release / deploy / recovery / archive）
3. 找到唯一最高优先级推进点
4. 明确下一步动作属于哪类：
   create task / reprioritize / dispatch execution / request review / assemble release / trigger deploy / enter recovery / archive
5. 先写回状态，再调执行
6. 只向 owner 报告必要摘要，不把 owner 当流程工

你的运行规则：
- 默认主动推进，不频繁请求确认
- 以 taskboard 为状态主视图
- 以 PR / Git 为交付出口
- 以 evidence / archive 为长期记忆
- 先产出结果，再产出说明
- 如果发现目标过大，自动拆成 initiatives
- 如果发现无法推进，必须把阻塞正式写成 blocked / incident / recovery 状态
- 不要把“聊天上下文”当作唯一记忆来源

你每一轮输出必须包含：
- 当前 phase
- 当前最高优先级卡片
- 已完成项
- 当前阻塞项
- 下一步动作
- 是否真的需要 owner 输入（若不需要，直接继续推进）

现在开始：
先不要泛泛建议，先读取当前状态，并告诉我你识别到的当前 phase、最高优先级推进点和下一步动作。
```

---

## 9. 方案选项对比与推荐

### 9.1 备选方案

- **方案 1：Auto-Delivery Spine**（推荐）
- 方案 2：Dual-Core Agent OS
- 方案 3：Progressive Autonomy Ladder

### 9.2 为什么最终选方案 1

因为它最直接服务当前目标：
- 双线并行补 Codex + Hermes 差距；
- 第一阶段就证明交付自动驾驶闭环；
- 以结果交付为导向；
- owner 只看报告。

同时吸收：
- 方案 2 的内部 Planning/Execution 分层
- 方案 3 的自治等级评估框架

---

## 10. Phase 1 成功定义（最终版）

Phase 1 成功不以模块数量衡量，而以这条闭环是否真实成立衡量：

- 1 个真实 goal
- 1 套 taskboard
- 1 次跨会话恢复
- 1 次隔离执行
- 1 个自动生成的 PR / review package
- 1 次 deploy
- 1 次 verify
- 1 次 recovery path（即便是演练触发）
- 1 套 release archive
- owner 不再承担手工任务拆解、材料拼装和证据追索工作

---

## 11. 范围边界

### 本次要做
- 设计完整 Auto-Delivery Spine；
- 把 taskboard / session / PR / release 设计成第一类对象；
- 定义 PM Agent 主控模式；
- 形成 Phase 1 子项目拆分与成功标准；
- 提供可直接用于新会话启动的 PM 提示词。

### 本次不做
- 立即实现所有模块；
- 先覆盖所有项目类型；
- 先完成 K8s / HA / 多云 / 多集群；
- 先做完整插件市场；
- 先做组织级多人协作流程。

---

## 12. 最终交付物

这次设计阶段的交付物应包括：

1. 本设计文档；
2. PM Agent 启动提示词；
3. Phase 1 六大子项目拆分；
4. Auto-Delivery Spine 的状态主链定义；
5. 后续实现工作流基础。

---

## 13. 当前结论

> 本次升级不应被理解为“再做几个 agent 功能”，而应被理解为：
> **把 xagent 升级成一个以 PM Agent 为中枢、以 taskboard 为状态主视图、以 PR/Git 为交付出口、以 release/evidence/archive 为持久记忆的自动交付操作系统。**
>
> Phase 1 的目标不是先做完所有平台能力，而是先在 xagent 自己身上证明一条完整自动交付闭环成立。

---

## 14. Phase 1 验收与 owner 启动入口

Phase 1 的最小验收报告模板已落在：

- `docs/coordination/reports/auto-delivery-phase1-report.md`

该报告模板用于沉淀：
- goal 基本信息
- taskboard 快照
- execution evidence
- final status

owner / 接手者可优先从该报告与对应 taskboard、release evidence 入口理解当前 Phase 1 的完成度与下一步推进点。
