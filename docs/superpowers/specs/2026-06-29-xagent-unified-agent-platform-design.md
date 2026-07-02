# X-Agent 全面 Agent 平台首发版设计说明

## 1．文档目标

本文档定义 X-Agent 首发版的目标形态：不是单点的 Coding Agent、Multi-Agent Gateway 或 Remote Assistant，而是一个面向 AI Native 代理工作室／运营团队的全面 Agent 平台。

首发版必须同时具备以下 4 类能力，并且在同一套运行时内完成统一交付：

1. **Codex 式执行与证据闭环**：真实执行、测试验证、失败可解释、结果可交付。
2. **OpenClaw 式多 Agent 路由与治理**：角色注册、能力匹配、策略化路由、隔离与审批。
3. **Hermes 式远程入口与持续运行**：Web、IM／Telegram、异步通知、阻塞恢复与长任务续航。
4. **X-Agent 自身优势并轨**：workflow view、企业审计、安全、多租户、creative workflow 全量并入统一平台。

本文档的设计结论用于指导后续的实现计划、模块拆分、接口收口与验证验收。

---

## 2．首发版产品定义

### 2.1 产品一句话定义

X-Agent 首发版是一个面向 AI Native 代理工作室／运营团队的统一任务运行平台，能够将需求、研究、编码、工作流编排、创意生产、远程协作、审计回放与最终交付收敛到同一套 Task／Run Runtime 中。

### 2.2 目标用户

首发版的第一优先用户是 **AI Native 代理工作室／运营团队**。

这类用户的共性包括：

- 同时处理开发、内容、运营、交付等复合任务。
- 需要多个 Agent 分工协作，而不是单个聊天机器人。
- 需要远程异步工作，不能把平台限定在本地浏览器停留期间。
- 需要可审计、可回放、可转交、可归档的交付结果。
- 需要私有部署优先，以便在工作室或项目团队内部快速落地。

### 2.3 首发版默认部署形态

首发版默认真形态为 **单机／工作室私有部署优先**。

设计要求如下：

- 支持 Docker Compose 或等价的工作室私有部署方式。
- 所有核心控制平面、运行时、审计与证据存储必须可在私有环境内独立运行。
- 远程入口、异步通知与长期运行能力必须在私有部署条件下成立，而不是依赖 SaaS-only 架构。
- 后续云端 SaaS 形态可以扩展，但首发版不以 SaaS 为第一部署目标。

---

## 3．产品总体设计结论

### 3.1 首发版不是功能拼盘，而是统一 Runtime 平台

X-Agent 首发版必须围绕统一运行时建模，而不是把下列能力各做一套：

- Coding Agent
- Workflow Engine
- Creative Studio
- Remote Assistant
- Audit Console

所有入口都必须进入同一套 Runtime，统一映射为：

- `Task`
- `Run`
- `StepExecution`
- `AgentAssignment`
- `Evidence`
- `Artifact`
- `ApprovalDecision`
- `DeliveryBundle`

### 3.2 首发版的一镜到底主链

平台首发版必须能完整演示以下超级场景：

> 用户提交一个新项目 brief 或复合需求，平台创建任务并生成运行实例；多个 Agent 根据策略自动拆解并并行执行研究、规划、编码、工作流编排与创意生产；任务在远程入口中持续运行、等待审批或补料时进入阻塞态；最终系统输出可审计、可交付、可回放、可恢复的结果包。

这个主链分为 5 段：

1. 任务接入
2. 多 Agent 拆解与编排
3. 真实执行与持续运行
4. 证据、产物与审批收束
5. 最终交付与回放

### 3.3 设计原则

首发版必须遵守以下原则：

1. **统一 Runtime 优先于功能堆叠**：新增能力必须挂到同一套 Task／Run 模型下。
2. **治理优先于自由调度**：多 Agent 协作必须受策略、隔离、审批和审计约束。
3. **证据优先于成功文案**：任务完成不是状态变绿，而是可证明完成。
4. **交付优先于日志堆积**：最终结果必须可消费、可转交、可归档。
5. **私有部署优先于云端假设**：首发版的一切核心能力必须可在工作室私有环境中成立。
6. **Creative 与 Coding 并轨**：创意生产不是旁支，而是与编码、工作流并列的一种任务主干。

---

## 4．首发版的 5 个核心子系统

### 4.1 Mission Control（任务与运行时中枢）

Mission Control 是平台的大脑，负责承接所有任务入口，统一创建 `Task` 与 `Run`，驱动阶段流转、状态管理、阻塞恢复、审批等待、回放恢复与最终收束。

它的职责包括：

- 创建与更新 Task／Run。
- 维护 Run phase、Run status、resume point。
- 根据任务类型切换到 coding spine、workflow spine、creative spine 或 hybrid spine。
- 管理 queued、planning、running、awaiting_approval、blocked、recovering、succeeded、failed 等运行态。
- 统一触发通知、交付、回放、恢复。

Mission Control 只关心任务如何流转，不关心具体由哪种 Agent 或执行器完成。

### 4.2 Agent Mesh（多 Agent 路由与治理层）

Agent Mesh 是多智能体系统的治理内核，负责：

- Agent Registry
- Capability Manifest
- Route／Binding Rules
- Agent-to-Agent Communication Policy
- Context Isolation Policy
- Tool Policy
- Sandbox Policy
- Escalation／Approval Policy

Agent Mesh 的目标不是“支持多个 Agent”，而是“让多个 Agent 的协作决策、权限范围与隔离边界可解释、可追踪、可约束”。

### 4.3 Execution Fabric（执行织布层）

Execution Fabric 负责统一调度不同类型的执行器，包括：

- Coding Executor
- Browser Executor
- Desktop Executor
- MCP／Tools Executor
- Creative／Media Executor
- Validation Executor

Codex 式执行闭环在这一层落地：命令执行、测试验证、Patch 生成、失败恢复、证据沉淀都由 Execution Fabric 驱动。

Creative Workflow、Browser Automation 与 Desktop Automation 也不应自成体系，而应作为不同的 Executor 类型纳入同一层。

### 4.4 Evidence & Delivery（证据与交付层）

Evidence & Delivery 负责将平台执行过程沉淀为：

- `Evidence`
- `Artifact`
- `ValidationSummary`
- `ApprovalDecision`
- `DeliveryBundle`

这一层决定平台是否真正具备竞争力。平台不能只告诉用户“任务成功了”，而必须能回答：

- 做了什么。
- 为什么这么做。
- 哪些验证通过了。
- 哪些风险仍然存在。
- 有哪些结果可以交付。
- 如何回放与继续。

### 4.5 Remote Ops Surface（远程协作与操作面）

Remote Ops Surface 负责统一 Web 工作台、IM／Telegram 入口、异步通知、远程审批、阻塞补料与持续运行的用户表面。

这不是一个轻量通知模块，而是 Hermes 式远程续航能力在 X-Agent 平台中的正式承载层。

---

## 5．统一数据模型

### 5.1 Task

`Task` 表示“用户想完成什么”。

建议字段：

- `task_id`
- `tenant_id`
- `workspace_id`
- `source`（web / api / im / schedule / creative / coding）
- `intent_type`（coding / workflow / creative / research / ops / hybrid）
- `goal`
- `requester`
- `priority`
- `policy_profile`
- `desired_outputs`
- `created_at`
- `updated_at`

Task 是业务目标对象，一个 Task 可以对应多次 Run。

### 5.2 Run

`Run` 表示一次真实执行实例，是全平台的第一主对象。

建议字段：

- `run_id`
- `task_id`
- `runtime_mode`（single-agent / multi-agent / creative / hybrid）
- `status`（queued / planning / running / awaiting_approval / blocked / failed / succeeded / cancelled / recovering）
- `current_phase`
- `entrypoint`
- `started_at`
- `finished_at`
- `resumed_from_run_id`
- `delivery_status`

所有 UI、审计、通知、交付、回放、恢复都围绕 Run 展开。

### 5.3 StepExecution

`StepExecution` 表示 Run 内部的执行单元。

建议字段：

- `step_id`
- `run_id`
- `parent_step_id`
- `kind`（plan / code / test / review / creative / media / approval / notify / handoff）
- `title`
- `assigned_agent_role`
- `assigned_executor_type`
- `depends_on`
- `status`
- `input_payload`
- `output_payload`
- `error`
- `retry_count`
- `started_at`
- `finished_at`

它统一承载 workflow node、coding step、creative node、approval gate 与 verification step。

### 5.4 AgentAssignment

`AgentAssignment` 记录“这一步为什么由这个 Agent 来做”。

建议字段：

- `assignment_id`
- `step_id`
- `agent_id`
- `role`
- `capability_match_result`
- `route_source`（manual / static_rule / planner / fallback）
- `communication_scope`
- `sandbox_scope`
- `tool_scope`
- `memory_scope`

这个模型是多 Agent 治理的关键落点。

### 5.5 Evidence

`Evidence` 表示可审查的执行证据。

建议字段：

- `evidence_id`
- `run_id`
- `step_id`
- `type`（command_output / test_result / trace / model_summary / approval_record / browser_capture / patch_summary / policy_decision）
- `source`
- `content_ref`
- `summary`
- `machine_verdict`
- `human_verdict`
- `created_at`

Evidence 用于证明过程，而不是承载最终交付本身。

### 5.6 Artifact

`Artifact` 表示真正交付出来的结果物。

建议字段：

- `artifact_id`
- `run_id`
- `step_id`
- `type`（code_patch / file_bundle / workflow_spec / canvas_snapshot / image / video / timeline / report / delivery_package）
- `uri`
- `preview`
- `version`
- `lineage`

Artifact 与 Evidence 必须严格区分：前者是结果，后者是证明。

### 5.7 ApprovalDecision

`ApprovalDecision` 统一承载审批行为。

建议字段：

- `approval_id`
- `run_id`
- `step_id`
- `approver_type`（human / policy / reviewer_agent）
- `approver_identity`
- `decision`（approved / denied / escalated / timed_out）
- `rationale`
- `scope`
- `created_at`

审批不是 workflow 特例，而是平台基础能力。

### 5.8 DeliveryBundle

`DeliveryBundle` 是最终面向用户或客户的交付包。

建议字段：

- `delivery_id`
- `run_id`
- `summary`
- `artifact_refs`
- `validation_summary`
- `approval_summary`
- `risk_summary`
- `replay_pointer`
- `export_formats`（web / pdf / zip / json）

DeliveryBundle 是平台对外输出的标准收束对象。

---

## 6．一镜到底主链设计

### 6.1 第一段：任务接入

平台支持以下入口进入统一 Runtime：

- Web 新建任务
- API／SDK
- IM／Telegram
- 定时调度
- Creative Brief
- Coding Issue／PR／Backlog Item

所有入口的接入动作统一为：

1. 创建 Task。
2. 创建 Run。
3. 进入 planning phase。
4. 根据任务类型选择 coding spine、workflow spine、creative spine 或 hybrid spine。

### 6.2 第二段：多 Agent 拆解与编排

Planner／Coordinator 负责将任务拆成执行图，例如：

- researcher：研究与检索
- planner：拆步骤与定义交付标准
- coder：改代码与实现能力
- reviewer：审查质量
- verifier：跑测试与验证
- operator：生成通知与交付包
- creative roles：screenwriter、director、editor_agent

此时 Agent Mesh 负责：

- capability match
- route／binding decision
- policy resolution
- 并行关系判定
- 审批门设置
- context sharing 约束
- sandbox 与 tool scope 分配

### 6.3 第三段：真实执行与持续运行

执行阶段必须允许混合任务同时存在，例如：

- coder 在隔离执行环境中改代码与跑测试。
- researcher 调 MCP、知识库与 Web。
- creative agent 生成 workflow draft、media 与 timeline。
- reviewer 对 Evidence 与 Artifact 做审核。
- remote operator 在 IM 中接收阶段通知与补料请求。

对于长任务，Run 必须支持：

- 持续运行
- 阻塞等待
- 审批暂停
- 失败 repair loop
- 从 resume point 恢复

### 6.4 第四段：证据、产物与审批收束

执行过程中每个关键步骤都必须产出：

- Evidence：日志、命令、测试、trace、策略决定
- Artifact：代码、文档、画布、素材、时间线、导出包
- Validation：对应类型的验证结果
- Approval：人工或策略审批记录

平台必须能让用户清晰回答：

- 谁做了什么。
- 为什么这么做。
- 哪一步成功或失败。
- 哪些产物已经形成。
- 哪些结果需要人工确认。

### 6.5 第五段：最终交付与回放

Run 结束后，系统自动形成 DeliveryBundle，并暴露：

- 任务摘要
- 关键产物
- 验证结果
- 审批记录
- 风险说明
- 完整 Timeline
- Replay／Resume 入口

失败态也必须具有标准收束面，不能直接掉入“无结果”状态。

---

## 7．控制平面与治理规则

### 7.1 Agent Registry

每个 Agent 必须有正式注册信息，而不能只是一段 Prompt 或一个 role 名称。

建议注册内容包括：

- `agent_id`
- `role`
- `description`
- `capability_manifest`
- `allowed_task_classes`
- `preferred_executor`
- `default_sandbox_scope`
- `default_tool_policy`
- `memory_visibility_policy`
- `communication_policy`
- `approval_escalation_policy`

### 7.2 Routing／Binding Rules

平台必须支持显式路由规则，并记录每次决策来源：

1. 静态规则：固定任务类型绑定固定 Agent。
2. Planner 规则：由 Planner 动态拆解后绑定。
3. Fallback 规则：默认代理或人工兜底。

每次路由都应留下：

- 规则来源
- 命中原因
- 候选 Agent
- 最终选择
- 回退原因

### 7.3 Context Isolation Model

上下文共享边界必须显式定义，建议分为 4 档：

1. `private`：仅当前 Agent 可见。
2. `team-shared`：同一 Run 中授权 Agent 可共享。
3. `artifact-shared`：只共享结构化产物，不共享全量上下文。
4. `tenant-visible`：租户内可审计、可归档的数据。

### 7.4 Tool Policy

工具权限不能默认开放，至少按 3 层收口：

- 全局层：平台允许的工具类别
- Agent 层：Agent 默认权限
- Step 层：单步临时扩权或降权

每次工具调用都应记录：

- policy version
- granted scope
- escalation requirement
- approval requirement
- actual tool used

### 7.5 Sandbox Policy

首发版必须显式区分执行环境：

- `none`
- `shared_workspace`
- `isolated_worktree_or_container`
- `browser_isolated`
- `creative_isolated`
- `elevated`

并定义：

- 默认沙箱策略
- 扩权触发条件
- 审批规则
- 失败后的回滚与清理方式

### 7.6 Approval Policy

审批必须支持 4 类情形：

1. 执行前审批
2. 结果审批
3. 策略审批
4. 人工接管审批

### 7.7 Tenant／Workspace Boundary

建议边界如下：

- `tenant`：商业或组织边界
- `workspace`：项目或工作室工作区边界
- `task`、`run`、`artifact`、`evidence`、`memory`、`schedule` 全挂在 workspace 下
- tenant 级策略可覆盖 workspace 默认策略

### 7.8 Audit as Native Projection

审计不应作为外部附加模块存在，而应作为 Runtime 的原生投影：

- Run 关键事件天然写入 audit projection。
- policy decision 天然可回查。
- approval 天然可归档。
- delivery bundle 天然关联审计摘要。

---

## 8．用户表面统一方案

### 8.1 首发版第一心智

用户看到的第一对象必须是：

- Task
- Run
- Inbox／Queue
- Delivery
- Replay

而不是先看到 chat、workflow、creative 或 settings 等二级能力页。

### 8.2 四个统一操作面

#### 8.2.1 Mission Inbox

Mission Inbox 承接所有任务来源，展示：

- 新任务
- 运行中任务
- 等待审批
- 等待补料
- 已完成交付

#### 8.2.2 Run Console

每个 Run 必须有统一控制台，至少包含：

- 概览
- Timeline
- Step Graph
- Active Agents
- Evidence
- Artifacts
- Approvals
- Validation
- Replay／Recovery

#### 8.2.3 Specialized Workspaces

复杂任务允许切换到专用工作区，但这些工作区必须是 Run 的投影，而不是独立产品：

- Coding Workspace
- Workflow Workspace
- Creative Workspace

#### 8.2.4 Delivery & Replay Surface

完成任务后，用户进入 Delivery & Replay Surface，查看：

- 交付摘要
- 导出包
- 验证结论
- 风险说明
- 回放与恢复入口

### 8.3 远程入口统一原则

远程入口只做两类事情：

1. 进入平台任务
2. 让平台运行继续

它不是主控制台的复制品，而是触发与续航层。

### 8.4 Creative 与 Coding 的统一原则

Creative 不应作为独立产品线存在，而应作为一种 Task Type、Execution Spine 与 Specialized Workspace 与 Coding、Workflow 并轨。

这样平台才能支持：

- coder 与 screenwriter 同时参与同一 Run
- workflow view 同时承载代码节点与内容节点
- delivery bundle 同时包含 patch、报告、timeline 与 media 导出物

---

## 9．验证、证据包与交付标准

### 9.1 “完成”的平台定义

平台中的“完成”必须同时满足：

1. **Execution Complete**：计划步骤已执行，无关键阻塞与未决强制审批。
2. **Validation Complete**：对应类型验证已运行，结果达到接受阈值，风险已显式记录。
3. **Delivery Ready**：产物可读、证据可审、回放可用、可导出与可转交。

因此：

> 完成 = 执行完成 × 验证完成 × 可交付完成

### 9.2 Validation Profile

首发版至少内置 4 类验证模板：

#### Coding Validation

- syntax／lint／typecheck
- targeted tests
- integration tests
- reviewer verdict
- regression summary

#### Workflow Validation

- step completeness
- routing policy satisfaction
- approval integrity
- replayability
- recovery point correctness

#### Creative Validation

- draft completeness
- required assets produced
- timeline／export integrity
- approval review status
- delivery readiness

#### Remote／Ops Validation

- notification delivered
- blocked／resume path valid
- run continuation consistent
- audit trail complete

### 9.3 Evidence Bundle

每个 Run 必须可生成 Evidence Bundle，至少包括：

- task summary
- run timeline
- agent assignments
- policy decisions
- tool invocations
- validation results
- approval decisions
- key logs／traces
- artifact references
- final risk summary

输出格式至少支持：

- Web 审阅视图
- JSON
- ZIP

### 9.4 Delivery Bundle

Delivery Bundle 用于对外交付，至少包括：

- 一页摘要
- 关键产物集合
- 验证结论
- 风险说明
- 下一步建议
- replay／resume 入口

### 9.5 Failure as Deliverable State

失败态也必须产品化收束，至少提供：

- failure summary
- blocking step
- evidence of failure
- suggested repair actions
- resume point
- escalation path

### 9.6 Replay／Recovery 进入交付面

回放与恢复不是内部调试能力，而必须成为交付面的一部分，至少支持：

- timeline replay
- graph replay
- evidence replay
- resume-from-step
- branch-from-run

### 9.7 首发版完成标准

平台首发版至少需要满足：

1. 任意任务都进入统一 Task／Run 模型。
2. 单 Agent 与多 Agent 都能真实执行。
3. coding、workflow、creative、remote 至少各有一条完整主链。
4. 每次 Run 都能生成 Evidence Bundle。
5. 每次完成态都能生成 Delivery Bundle。
6. 审批、恢复、回放是平台原生能力。
7. 多租户与审计边界不能被旁路绕过。

---

## 10．首发版非目标

为了避免平台再次发散，以下内容不作为首发版新增目标：

1. 以 SaaS 为前提的云端控制面重写。
2. 大规模插件市场生态化运营能力。
3. 面向大众消费者的轻量聊天产品形态。
4. 与首发主链无关的 UI 视觉翻新优先级高于 Runtime 收口。
5. 为了“显得全面”而继续扩展未进入主链的适配器名录。

这些能力可以存在于平台后续阶段，但不能挤占首发版的统一 Runtime 与交付闭环建设。

---

## 11．与现有 X-Agent 的并轨要求

首发版不是另起炉灶，而是要求现有 X-Agent 的能力收口并轨到统一 Runtime 中。

必须并轨的现有优势包括：

- workflow structured view
- timeline
- approval／replay 语义
- 企业审计链
- 多租户安全边界
- creative workflow draft
- canvas／timeline／export 产线

并轨原则如下：

1. 保留现有差异化语义，不做功能降级。
2. 把现有差异化能力挂到统一 Task／Run 模型下。
3. 不再允许 workflow、creative、audit 各自维持独立主模型。
4. 前端工作台必须围绕统一 Run Console 和 Delivery Surface 重组。

---

## 12．最终设计结论

X-Agent 首发版必须被设计为一个 **Run-centric 的统一 Agent 平台**。

它不是某一个竞品的复制品，而是：

- 用 Codex 的执行与证据闭环，建立真实交付能力。
- 用 OpenClaw 的多 Agent 路由与治理，建立平台级协作能力。
- 用 Hermes 的远程入口与持续运行，建立异步续航能力。
- 用 X-Agent 原有的 workflow view、creative workflow、审计、安全、多租户，建立差异化价值。

首发版的真正竞争力不来自“功能更多”，而来自：

> 所有能力被收敛到同一套 Runtime 中，并能在私有部署环境下稳定地产生可执行、可审计、可回放、可交付的结果。
