# X-Agent Web/API 发布硬化与竞品差距补齐设计

> 日期：2026-08-07
>
> 状态：已获 Owner 批准进入执行
> 当前交付面：Web + API

## 1. 目标

将 X-Agent 的 Web/API 版本从“功能骨架已存在”推进到可复现、可审查、可恢复的发布状态，并补齐相对 OpenAI Codex 与 Hermes Agent 的关键产品深度。

完成后必须同时满足：

1. 并发工具执行不会把成功调用误报为运行时异常。
2. CI 不再吞掉未定义变量等高风险静态错误，发布只能发生在完整门禁成功之后。
3. 并行编码任务的 worktree 结果可以在 Web 中查看、审查、接受、拒绝或导出，不再执行后立即销毁。
4. 定时任务具有持久运行记录、重试、重启恢复和 Web 管理入口。
5. SKILL.md 导入保留完整技能包，不再只截取正文提示。
6. 会话和 checkpoint 可以查询、恢复与回滚，并通过 API 与 Web 暴露真实状态。
7. X-Agent MCP 服务扩展到会话、运行、审批和事件读取，而不只提供 4 个一次性工具。

## 2. 范围边界

### 2.1 本阶段包含

- FastAPI 后端、React Web 前端、Web/API Docker 镜像及相关 CI。
- 编排内核、并行 Agent、worktree 生命周期、代码审查、调度器、技能包、会话/checkpoint、平台 MCP 服务。
- Web/API 发布文档、版本口径、测试矩阵和发布证据。

### 2.2 本阶段不包含

- 短剧工厂的模型、媒体生成、画布、剪辑和行业交付链路。
- Tauri 桌面端的图标、打包、签名、自动更新与发布门禁。
- 多机 HA、云托管编码任务、E2B 商用验证和客户现场异构环境演练。
- DSPy/GEPA 等重型提示优化框架。

短剧与桌面代码不删除。Web 正式交付入口默认不展示短剧能力，待独立短剧项目稳定后通过单独集成规格接入。

## 3. 当前基线与已确认缺陷

### 3.1 可用基线

- `apps/api/tests/test_orchestration.py`：10/10 通过。
- Web 单元测试：3/3 通过。
- Web typecheck：通过。
- Web production build：通过。
- Web lint：0 error / 100 warnings。

### 3.2 P0 已确认缺陷

- `core/orchestration/loop.py` 的流式并发工具嵌套函数修改 `_tool_success` 和 `_tool_fail` 时缺少正确的状态传递，实际双工具调用稳定产生 `UnboundLocalError`。
- Ruff 已定位 2 个 `F823` 和 3 个 `B023`，但 CI 使用 `|| true` 忽略结果。
- mypy 当前同样使用 `|| true`，无法形成可发布门禁。
- README 仍宣称版本 `0.1.0`，而 API/Web/tag 已为 `1.0.0`。
- v1.0.0 Release 创建早于 tag CI 完成；仓库没有“全部发布门禁成功后再创建 Release”的自动化约束。

### 3.3 竞品深度缺口

- worktree 只采集截断 diff，随后强制删除 worktree 和分支，没有人工审查与落地生命周期。
- Scheduler 使用本地 JSON 作 job 存储，缺少 run history、attempt、通知、崩溃回收和 Web 页面。
- SKILL.md 导入只映射摘要提示，未保留 `references/`、`scripts/`、`assets/` 和完整正文。
- checkpoint 是本机短期 JSON，过期时间固定为 30 分钟，没有 API、租户隔离和 rollback 生命周期。
- Platform MCP Server 只有 run、review、skill match、skill import 4 个工具。

## 4. 总体架构

按依赖关系分为 3 个阶段，每个阶段都必须形成独立的测试、迁移、API、Web 和证据闭环。

```text
P0 发布可信基线
  ├─ 运行时正确性
  ├─ 静态质量阻断
  ├─ Web 发布范围与版本口径
  └─ CI 成功后发布
          ↓
P1 Codex 开发任务闭环
  ├─ 持久 worktree 运行记录
  ├─ diff / review / approve / reject / export
  ├─ apply/cherry-pick 冲突状态
  └─ Web 开发任务控制台
          ↓
P2 Hermes 持久自治闭环
  ├─ durable scheduler + run history + retry/recovery
  ├─ 完整 Skill Package
  ├─ session/checkpoint/rollback
  └─ MCP 会话、审批与事件接口
```

## 5. P0：发布可信基线

### 5.1 并发工具执行

流式和非流式工具路径必须使用同一份显式执行结果模型：

```text
ToolExecutionOutcome
  name
  call_id
  text
  ok
  elapsed_seconds
```

单工具协程只返回结果，不直接修改外层计数器。聚合阶段按结果统一更新成功数、失败数、按工具类型统计和事件。这消除闭包局部变量错误，也避免并发协程共享可变计数状态。

回归测试必须构造 2 个流式原生 tool call，断言：

- 两个真实工具结果均回填；
- 结果中没有 `UnboundLocalError`；
- 成功/失败统计与事件一致；
- 第二轮模型调用前存在配对的 tool message。

### 5.2 静态质量门禁

CI 采用渐进式阻断，不伪装一次清完全部存量问题：

- 立即阻断：`F821,F822,F823,B023`。
- 立即报告且建立固定基线：完整 Ruff、mypy。
- 每个后续任务只能降低基线，不能新增错误。
- P2 完成前，完整 Ruff 与 mypy 必须归零或形成逐文件、带理由和失效日期的最小豁免。

### 5.3 Web 发布范围

- 正式导航与默认路由不展示短剧入口。
- 直接访问已排除入口时显示“当前 Web/API 发布不包含此模块”，不宣称能力可用。
- 桌面端不进入本阶段 CI 和 Release 资产。
- README、状态事实源和发布检查表明确当前发布边界。

### 5.4 Release 顺序

tag push 先运行完整 Web/API gate。只有 backend、frontend、license、config、API E2E、load、eval 和 Docker image 全部成功，Release job 才能创建或更新 GitHub Release。Release job 必须校验 tag 版本与 API/Web 版本一致。

## 6. P1：Codex 开发任务闭环

### 6.1 状态模型

并行子任务新增持久状态：

```text
running → awaiting_review → approved → applied
                    ├──────→ rejected
                    ├──────→ conflict
                    └──────→ expired
```

每个任务保留：租户、创建者、主工作区、基线 commit、临时分支、worktree 路径、结果 commit、diff stat、完整 patch 路径、测试摘要、状态和审计时间。

### 6.2 Git 生命周期

1. 从固定基线 commit 创建临时分支和 worktree。
2. Agent 完成后，在临时分支创建结果 commit；未提交文件不得被静默丢弃。
3. `awaiting_review` 状态保留 worktree、分支和 patch。
4. Approve 只表示审查通过；Apply 在显式权限检查后将结果 commit cherry-pick 到目标分支。
5. 冲突时保留双方状态并返回冲突文件，不自动覆盖。
6. Reject 或过期清理 worktree/branch，但保留审计记录和 patch 摘要。

### 6.3 Web 控制台

Web 提供开发任务列表与详情：

- 子任务状态、耗时、模型、基线 commit；
- 文件级 diff 和测试摘要；
- Approve、Reject、Apply、Download Patch；
- 运行中的 cancel/interrupt；
- 冲突文件与人工恢复说明。

所有变更动作都要求明确确认，并写入现有审计链。

## 7. P2：Hermes 持久自治闭环

### 7.1 Durable Scheduler

Job 与 Job Run 使用数据库持久化，不再以 JSON 文件作为发布路径事实源。

Job Run 至少记录：`scheduled_for`、`claimed_at`、`started_at`、`finished_at`、`status`、`attempt`、`run_id`、`error`、`next_retry_at` 和通知结果。

调度规则：

- 数据库原子 claim + Redis lease 防止重复执行；
- 服务启动时回收租约过期的 `running` 记录；
- 指数退避，默认最多 3 次；
- missed run 默认只补最近 1 次，避免重启后洪峰；
- Web 可查看历史、手动重跑、暂停和删除；
- 终态通过现有 webhook 通知，通知失败不改变任务终态，但单独记录。

### 7.2 Skill Package

技能导入支持目录或 ZIP，安全解包后保留：

- 原始 `SKILL.md`；
- frontmatter；
- 完整正文；
- `references/`、`scripts/`、`assets/`；
- 内容摘要、SHA-256、来源和导入时间。

拒绝绝对路径、`..` 穿越、符号链接逃逸和超限文件。运行时仍由现有技能匹配器选择技能，但提示注入引用完整正文；脚本执行继续受工具权限和 sandbox 限制。

### 7.3 Session 与 Checkpoint

Checkpoint 进入数据库并绑定 tenant、conversation、run 和 step。API 提供列表、查看、恢复和回滚；恢复创建新 run 并记录 parent checkpoint，不覆盖历史。回滚文件改动必须通过 Git commit/patch 执行，禁止按不可信路径直接覆盖工作区。

Web 在对话和 Run Console 中展示 checkpoint 时间线、恢复来源和 rollback 结果。

### 7.4 Platform MCP

在现有工具之上增加：

- conversation list/get/message；
- run get/cancel/events；
- approval list/resolve；
- scheduler job/run read；
- skill package read。

所有 MCP 调用复用现有 Principal、租户隔离、权限检查和审计，不建立第二套安全模型。

## 8. 数据与迁移原则

- 新持久模型使用 SQLAlchemy/Alembic，SQLite 用于本地验证，PostgreSQL 为 full 模式发布路径。
- 所有查询必须显式包含 tenant 约束。
- 文件型 artifact 只保存不可执行数据或受控技能包，数据库保存路径、摘要和所有权。
- 迁移必须支持从现有 v1.0.0 schema 前向升级，不修改历史 migration。

## 9. 错误处理与安全

- Git、scheduler、checkpoint 和 MCP 的失败必须形成结构化状态，不能仅记录日志后返回成功。
- Apply、rollback、脚本运行和外部通知属于高风险动作，沿用现有权限模式与审批机制。
- worktree 路径、skill archive 路径和 patch 路径必须限制在配置的受控根目录。
- token、secret、环境变量和值守信息不得进入 diff、checkpoint、通知或 MCP 事件正文。

## 10. 验收与发布证据

每个任务完成前必须提供：

- 先失败后通过的最小回归测试；
- 相关模块测试；
- 静态检查；
- API 契约测试；
- Web 单元测试、typecheck、lint 和 build；
- 关键 Web 流程 Playwright；
- migration upgrade 验证；
- `git diff --check` 和精确变更清单。

最终发布必须证明：

1. Web/API release gate 全绿且没有 `|| true` 掩盖阻断项。
2. 并行代码任务能从创建走到 review、apply/reject 和 cleanup。
3. scheduler 在进程重启后能恢复未完成记录并按策略重试。
4. 完整 Skill Package 可导入、读取和安全拒绝恶意 archive。
5. checkpoint 能恢复为新 run，并保留父子审计关系。
6. MCP 能读取同一会话/run/审批状态且租户隔离成立。
7. README、事实源、版本和 Release Notes 与真实验证范围一致。

## 11. 交付顺序

1. P0-A：流式并发工具执行回归与修复。
2. P0-B：关键 Ruff 门禁、闭包风险修复与 mypy/Ruff 基线。
3. P0-C：Web 发布范围、版本事实源和 CI 后发布。
4. P1-A：worktree 结果持久模型与 Git 生命周期。
5. P1-B：审查/apply API 与 Web 开发任务控制台。
6. P2-A：durable scheduler、运行历史、重试恢复与 Web 页面。
7. P2-B：完整 Skill Package 导入、存储与安全门禁。
8. P2-C：数据库 checkpoint、恢复/回滚与 Web 时间线。
9. P2-D：MCP 会话、运行、审批、事件接口。
10. 发布级全量审计、文档一致性检查与 Release gate 实跑。
