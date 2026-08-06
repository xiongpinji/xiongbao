# Web/API P1 开发任务闭环实现计划

## 目标与边界

将现有“并行 worktree 执行后截断 diff 并立即删除”的临时能力升级为可持久审查的开发任务闭环：`running → awaiting_review → approved → applied`，并支持 `rejected / conflict / expired / failed / timeout / cancelled`。本计划只覆盖 Web/API 与 Git 本地生命周期，不包含短剧、Tauri 桌面、远端 PR 托管或 P2 持久调度。

成功标准：

1. 成功的隔离子任务保留结果 commit、worktree、分支和完整 binary patch，直到 apply/reject/expire。
2. 任务记录按 tenant/owner 持久化，服务重启后仍可查询。
3. Approve 不修改目标分支；Apply 必须显式确认，并以 cherry-pick 落地。
4. 冲突时自动 abort cherry-pick，主工作区恢复干净，任务记录冲突文件。
5. Reject/Apply/Expire 清理 worktree 与临时分支，但保留记录和 patch。
6. Web 能查看列表、详情、文件级 patch、测试摘要，并执行 approve/reject/apply/cancel。

## 约束与取舍

- 复用 `core/orchestration/parallel.py`、现有 RBAC、审计链和异步 SQLAlchemy，不再建立第二套任务运行时。
- patch 保存到主仓库同级 `.xagent-development-tasks/<task_id>.patch`；worktree 保存到同级 `.xagent-worktrees/<task_id>`。两者均不依赖目标仓库 `.gitignore`，所有路径先解析并验证位于受控根下。
- API 不返回内部绝对路径，只返回任务元数据和按权限读取的 patch 内容。
- P1 不自动 merge/rebase、不覆盖脏工作区、不自动解决冲突。
- 现有非 worktree 并行模式保持兼容；只有 `use_worktrees=true` 创建开发任务记录。
- 现有同步并行请求暂不改成 durable queue；运行中 cancel 只保证当前 API 进程内有效，跨重启恢复属于 P2。

## 任务 1：持久模型、迁移与仓储

**文件：**

- 创建：`apps/api/xagent/infra/models/development_task.py`
- 创建：`apps/api/xagent/domains/development_tasks/__init__.py`
- 创建：`apps/api/xagent/domains/development_tasks/models.py`
- 创建：`apps/api/xagent/domains/development_tasks/service.py`
- 创建：`apps/api/migrations/versions/20260807_development_tasks.py`
- 修改：`apps/api/xagent/infra/models/__init__.py`
- 创建：`apps/api/tests/test_development_tasks.py`

- [x] 先写失败测试：创建 `running` 记录，更新为 `awaiting_review`，重新开 session 后按 tenant 查询仍存在；另一 tenant 查询不到。
- [x] ORM 字段覆盖 task/run/tenant/owner、goal/status、workspace/base/target/work branch、worktree/result commit、diff stat、patch/test/conflict/error、创建/更新/审查/应用/过期时间。
- [x] domain service 只接受显式 tenant，提供 create/get/list/update；状态序列化使用固定字符串枚举。
- [x] migration 以 `20260805_users_persist` 为 parent，并安全创建索引。
- [x] 验证：`pytest test_development_tasks.py -q`、migration upgrade/head、关键 Ruff。

## 任务 2：受控 Git 资产与保留生命周期

**文件：**

- 创建：`apps/api/xagent/domains/development_tasks/git_lifecycle.py`
- 修改：`apps/api/xagent/core/orchestration/parallel.py`
- 修改：`apps/api/tests/test_parallel_worktrees.py`

- [x] 先把现有“成功后已清理”的测试改为失败契约：成功结果必须为 `awaiting_review`，worktree/branch/patch/commit 均存在，主工作区仍干净。
- [x] 创建 `DevelopmentTaskPaths` 并验证 worktree/patch 解析路径不能逃逸受控根。
- [x] worktree 固定从 base commit 创建；完成后 `git add -A`、创建结果 commit、生成完整 `--binary` patch；API preview 仍最多 4000 字符。
- [x] 并行结果增加 `development_task_id` 和 `development_task_status`。
- [x] Agent failed/timeout 时写终态并清理临时 Git 资产；cancelled 在任务 3 接入运行注册表时完成。
- [x] 验证成功保留、失败清理、无 Git 仓库诚实降级和序列化回归。

## 任务 3：Approve、Reject、Apply、Conflict、Cancel

**文件：**

- 修改：`apps/api/xagent/domains/development_tasks/service.py`
- 修改：`apps/api/xagent/domains/development_tasks/git_lifecycle.py`
- 修改：`apps/api/xagent/core/orchestration/parallel.py`
- 修改：`apps/api/tests/test_development_tasks.py`

- [x] 先写状态机失败测试：非法迁移拒绝；approve 不改主分支；reject 清理；apply cherry-pick；冲突 abort 后主工作区无未合并文件。
- [x] approve 只写状态与 reviewed_at。
- [x] reject/expire 清理 worktree/branch并保留 patch/记录。
- [x] apply 要求 `approved`、目标 workspace 为干净 Git repo；cherry-pick 成功后写 applied commit/时间并清理。
- [x] cherry-pick 冲突收集 unmerged files、执行 `--abort`、写 `conflict`。
- [x] 进程内运行注册表支持 cancel 当前 asyncio task；DB 写 `cancelled`，跨重启不作虚假保证。

## 任务 4：租户隔离 API 与审计

**文件：**

- 创建：`apps/api/xagent/api/v1/development_tasks.py`
- 修改：`apps/api/xagent/api/v1/__init__.py` 或当前 router 注册文件
- 修改：`apps/api/xagent/api/v1/automation.py`
- 创建：`apps/api/tests/test_development_tasks_api.py`

- [ ] 先写 API 失败测试：list/detail tenant 隔离；approve/reject/apply/cancel 缺显式确认返回 422；patch 不暴露路径。
- [ ] GET `/development-tasks`、`/{id}`、`/{id}/patch` 使用 `agent:read`。
- [ ] POST approve 使用 `code_review:execute`；reject/apply/cancel 使用 `agent:execute`，body 必须携带 task id 确认值。
- [ ] 所有动作写现有 audit chain；404 不泄露另一 tenant 的存在。
- [ ] parallel-run 响应返回 development task id，便于 Web 跳转。

## 任务 5：Web 开发任务控制台

**文件：**

- 创建：`apps/web/src/api/developmentTasks.ts`
- 创建：`apps/web/src/pages/DevelopmentTasksPage.tsx`
- 修改：`apps/web/src/App.tsx`
- 修改：`apps/web/src/shell/shellRoutes.ts`
- 修改：`apps/web/src/tests/shellNavigation.test.ts`
- 创建：`apps/web/src/tests/developmentTasks.test.ts`

- [ ] 先写导航与状态动作失败测试。
- [ ] 主导航增加“开发任务”，route `/development-tasks`，使用 workflow 类型而非新增无关 shell 抽象。
- [ ] 列表显示状态、目标、耗时/更新时间、base/result commit；详情显示 diff stat、完整 patch、测试摘要、冲突文件。
- [ ] 按状态只展示合法动作；approve/reject/apply/cancel 均二次确认，并显示服务端错误。
- [ ] Web 默认测试入口自动发现新测试；lint warning 不得超过 100。

## 任务 6：P1 审计与证据

**文件：**

- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`
- 创建：`docs/coordination/reports/WEB_API_P1_DEVELOPMENT_TASK_LOOP_EVIDENCE.md`

- [ ] 后端运行 development task、parallel worktree、API、code review 相关测试。
- [ ] 运行 migration fresh upgrade、关键 Ruff、静态质量基线。
- [ ] Web 运行 test/lint/typecheck/build。
- [ ] 在临时 Git repo 实跑 create → awaiting_review → approve → apply，以及 create → reject、冲突 → abort。
- [ ] 证据报告记录退出码、状态链、commit/patch/worktree 清理和剩余风险；P1-A/P1-B 转 DONE，P2-A 转 READY。
