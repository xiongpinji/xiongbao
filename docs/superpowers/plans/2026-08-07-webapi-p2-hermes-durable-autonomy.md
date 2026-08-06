# Web/API P2 Hermes 持久自治闭环实现计划

## 目标与边界

以 SQLAlchemy/Alembic 为持久事实源，依次补齐 durable scheduler、完整 Skill Package、会话/checkpoint 恢复和 Platform MCP 读接口。只实现 Web/API，不包含短剧、Tauri 桌面、多机 HA 现场演练或远程 PR 托管。

成功标准：

1. scheduler 在重启后从数据库恢复 job/run，过期 running lease 可回收，失败按指数退避最多 3 次。
2. Skill Package 保留完整 SKILL.md 与 references/scripts/assets，ZIP 导入拒绝穿越、符号链接和超限内容。
3. checkpoint 按 tenant/conversation/run/step 入库；resume 创建新 run 并保留 parent，rollback 只通过受控 Git commit/patch。
4. MCP 读取 conversation/run/approval/scheduler/skill package 复用同一 Principal、RBAC、tenant 过滤和审计链。
5. Web 能查看调度历史与 checkpoint 时间线，且所有状态变更显式确认。

## P2-A：Durable Scheduler

**任务 1：数据模型、迁移与仓储**

- 创建 `scheduled_jobs` 与 `scheduled_job_runs`，包含 tenant/owner、schedule、lease、attempt/retry、run/error/notification 和完整时间字段。
- 先写失败测试：持久、tenant 隔离、到期 claim 只能成功一次、最多补最近一次。
- 全新 SQLite upgrade 和 PostgreSQL 可移植 SQLAlchemy 语义均通过。

**任务 2：调度循环、租约与重试恢复**

- 用 DB job 替代 JSON 事实源；Redis lease 保留为多实例第二道防线。
- 原子创建/claim Job Run，结构化写入 queued/running/succeeded/failed/retry_wait/interrupted。
- 启动回收过期 lease；指数退避且最多 3 次；missed run 只补最近一次。
- 通知失败只写 notification_error，不改任务终态。

**任务 3：租户隔离 API 与审计**

- list/get/create/pause/delete/manual retry/run history 全部显式 tenant 过滤。
- 变更操作必须确认 job/run ID，跨租户统一 404，写 audit chain。
- 保留旧 API 路径，但收紧错误码和返回结构。

**任务 4：Web 调度中心**

- 增加 `/scheduler`、主导航、job 列表、run 历史、失败/重试信息。
- pause/delete/retry 二次确认，页面错误不吞掉。
- Web 单测、typecheck、lint/build 和 Playwright 真实页面。

## P2-B：完整 Skill Package

- 数据库记录 package tenant/owner/name/version/hash/manifest/root/imported_at。
- 受控包根保留原始 SKILL.md 和 references/scripts/assets；运行匹配器引用完整正文。
- ZIP/目录导入上限：文件数、单文件、总解压大小；拒绝绝对路径、`..`、符号链接和重复路径。
- API/Web 展示 manifest/hash/来源，脚本不因导入而自动执行。

## P2-C：Session / Checkpoint / Rollback

- checkpoint 数据库模型绑定 tenant/conversation/run/step，消息和变更文件作脱敏后 JSON 存储。
- list/get/resume API；resume 产生新 run 和 parent_checkpoint_id，不覆盖原历史。
- rollback 只接受已验证的 Git patch/result commit，脏工作区或路径逃逸必须拒绝。
- Web 在对话/Run Console 展示时间线、恢复来源和 rollback 结果。

## P2-D：Platform MCP

- 新增 conversation list/get/message、run get/cancel/events、approval list/resolve、scheduler job/run read、skill package read。
- MCP tool handler 必须从已认证 Principal 调用现有 domain service，禁止直接跨 tenant 读全局 store。
- 契约测试覆盖同租户与跨租户，变更动作写审计链。

## 阶段审计

- 每个数据包都必须 fresh migration、失败先行测试、相关回归和关键 Ruff。
- 每个 Web 包都必须默认测试自动发现、lint 不反弹、typecheck/build 和 Playwright。
- P2 收口时全量 Ruff/mypy 必须归零，或将仍存的每个问题形成带理由、owner 和失效日期的最小豁免，不得仅保留总数基线。
- P2-D 后创建统一证据报告，再进入 R1 Release gate 实跑。
