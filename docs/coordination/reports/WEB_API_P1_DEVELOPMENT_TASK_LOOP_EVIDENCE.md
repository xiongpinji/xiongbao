# Web/API P1 开发任务闭环证据

## 结论

- 审计日期：2026-08-07。
- 分支：`feature/webapi-release-hardening`。
- 审计范围：P1 可持久开发任务、Git worktree 生命周期、审查/应用 API 和 Web 控制台。
- 排除范围：短剧、Tauri 桌面、远程 PR 托管、跨进程任务恢复。
- 结论：P1 通过，Codex 类“隔离修改 → 审查 → 显式应用”的本地 Web/API 闭环已成立；总目标仍未完成，下一阶段为 Hermes 类持久调度、Skill Package 和会话恢复。

## 状态链与 Git 证据

| 验证 | 结果 |
|---|---|
| 持久仓储 | task/run/tenant/owner、Git 基线与分支、patch、测试、冲突和审查时间均落库；重开 session 后可查 |
| 成功任务 | 从固定 base commit 创建 worktree，产生 result commit 和完整 `--binary` patch，状态为 `awaiting_review` |
| Approve | 仅写 `approved` 及审查人/时间，不修改目标分支 |
| Apply | 要求已批准、目标分支匹配且主工作区干净；cherry-pick 成功后清理 worktree/分支 |
| Conflict | 收集冲突文件并自动 `cherry-pick --abort`，主工作区无未合并文件 |
| Reject / Expire | 清理 worktree 与临时分支，保留任务记录与 patch |
| Failed / Timeout / Cancel | 写明确终态并清理临时 Git 资产；cancel 当前只保证同 API 进程 |

`test_development_task_lifecycle.py` 使用临时真实 Git 仓库执行 approve/apply、reject、conflict/abort、expire 与脏工作区拒绝，不是 fixture 文本模拟。

## API、租户与审计

| 验证 | 结果 |
|---|---|
| 相关后端回归 | 退出码 0，31/31 通过 |
| list/detail 租户隔离 | 只返回当前 tenant；跨租户 detail 统一 404 |
| 变更确认 | approve/reject/apply/cancel 缺 `confirm_task_id` 均 422，不匹配为 409 |
| RBAC | 读取使用 `agent:read`，approve 使用 `code_review:execute`，其余动作使用 `agent:execute` |
| 路径脱敏 | list/detail/patch 响应不含 main workspace、worktree 或 patch 绝对路径 |
| 审计 | 变更动作写入既有 hash audit chain，记录 tenant、actor、task ID 和结果状态 |
| 并行响应 | worktree 子任务返回 `development_task_id` 与 `development_task_status` |

回归命令覆盖 `test_development_tasks.py`、`test_development_task_lifecycle.py`、`test_parallel_worktrees.py`、`test_development_tasks_api.py` 和 `test_code_review.py`。一次将该回归与全仓静态扫描并发时，双 worktree 用例曾因资源竞争返回 `partial`；同用例单跑 1/1、整组串行重跑 31/31 通过。

## 迁移与静态质量

| 验证 | 结果 |
|---|---|
| 全新 SQLite `alembic upgrade head` | 退出码 0，head=`20260807_development_tasks` |
| 表回读 | `sqlite_master` 实际返回 `development_tasks` |
| 关键 Ruff `F821,F822,F823,B023` | 退出码 0，0 项 |
| 静态基线 | Ruff `279 <= 286`，mypy `73 <= 74` |

## Web 与真实浏览器

| 验证 | 结果 |
|---|---|
| `npm test` | 退出码 0；自动发现 3 个测试文件，14/14 通过 |
| ESLint JSON 统计 | 0 error / 100 warnings，未超 P0 基线 |
| `npm run typecheck` | 退出码 0 |
| `npm run build` | 退出码 0，2374 modules transformed，产生独立 `DevelopmentTasksPage` chunk |
| Playwright 真实浏览器 | 隔离 lite API + Vite 实际启动；登录后侧栏可见“开发任务”，点击进入 `/development-tasks`，页面标题、选中态、刷新和空状态正确 |

首次真实浏览器快照暴露了侧栏手写导航缺失；修复后重新快照已看到可点击入口和正确激活态。控制台端到端本轮只验证空状态；有数据动作由 Web 动作矩阵、API 端到端和真实 Git 生命周期测试分层覆盖。

## P1 实现提交

- `dc0735c`：增加持久开发任务模型与租户隔离仓储。
- `4877e36`：保留可审查 worktree、result commit 和完整 patch。
- `f6e4c74`：增加 approve/reject/apply/conflict/expire/cancel 状态机。
- `e348964`：增加租户隔离审查 API、显式确认与审计。
- `72245a0`：增加 Web 开发任务审查控制台。
- `9946b91`：修复真实浏览器发现的侧栏入口缺失。

## 已知剩余风险

- 运行中 cancel 依赖当前 API 进程内 asyncio task 注册表；服务重启后恢复属于 P2。
- 完整 patch 由受权读接口一次返回；超大 patch 的分页/流式化仍是后续性能工作。
- 本地 P1 不提供 GitHub/GitLab PR 托管，也不自动 merge/rebase 或解决冲突。
- 同一 PowerShell 进程串行执行多个 npm 命令时，Node 24 曾在 Vite 已构建成功后触发一次 Windows libuv 断言；独立构建和后续串行 typecheck/build 均退出 0。
- Playwright 控制台仅有已存的 favicon 404 和 React Router v7 future-flag 警告，本轮未扩大范围修复。
- P0 的存量 Ruff/mypy/Web warning 基线仍存在，且远端 CI 尚未由该本地分支触发。
