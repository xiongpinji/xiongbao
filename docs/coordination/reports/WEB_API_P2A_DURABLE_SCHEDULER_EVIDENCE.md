# Web/API P2-A 持久调度闭环证据

## 结论

- 审计日期：2026-08-07。
- 分支：`feature/webapi-release-hardening`。
- 审计范围：数据库持久任务/运行、原子领取、Redis 二级租约、崩溃恢复、有界重试、终态 Webhook、租户 API、Web 调度中心。
- 排除范围：短剧、Tauri 桌面、多机 HA 压测和客户现场演练。
- 结论：P2-A 通过。调度任务已从旧 JSON 触发路径切换为数据库运行事实源，Web/API 可创建、暂停、恢复、删除、手动运行和读取历史；总目标仍未完成，下一阶段为 P2-B Skill Package。

## 数据库调度与恢复

| 验证 | 结果 |
|---|---|
| 持久模型 | `scheduled_jobs`、`scheduled_job_runs` 保存 tenant/owner、计划时间、attempt、claim token、lease、结果、错误、重试和通知状态 |
| 原子 claim | 数据库条件更新先推进 `next_run`，并只创建一个 run；并发第二次领取返回空 |
| 错过计划 | 只补最近一次到期运行，下一次从当前领取时间向后推进，不回放历史洪峰 |
| 启动恢复 | 过期 `running` lease 转 `interrupted` 并进入重试队列 |
| 有界重试 | 默认最多 3 次重试，指数退避；达到上限后写 `failed` |
| 暂停边界 | 已暂停任务不消费普通 retry；显式手动运行 attempt 0 仍可领取 |
| Redis 二级租约 | 配置 Redis 时，先取得 job 级 360 秒所有者租约，再做数据库原子 claim；拒绝租约不生成 run；执行结束以 `WATCH/MULTI/EXEC` 仅释放自己的锁 |
| 终态通知 | 仅 `succeeded/failed` 发 `scheduler.job_run.completed`；HTTP 非 2xx 和异常写独立通知失败，不改变任务终态 |
| 重启后 Webhook | 启动时恢复全部租户持久 Webhook，不再只恢复 `default` 租户 |

## API、Web 与真实浏览器

| 验证 | 结果 |
|---|---|
| 租户 API | list/create/delete/toggle/history/manual-run 均按 principal tenant 读取或变更；跨租户历史返回 404 |
| 变更确认 | delete/toggle/manual-run 要求精确 job ID 确认，并写既有审计链 |
| Web 页面 | `/scheduler` 提供创建、启停、立即运行、删除及运行历史；状态、attempt、下次重试、错误和结果可见 |
| `npm test` | 退出码 0；自动发现并执行 17/17 |
| `npm run typecheck` | 退出码 0 |
| `npm run lint` | 退出码 0；0 error / 100 条存量 warning，未反弹 |
| `npm run build` | 退出码 0；2376 modules transformed，生成独立 `SchedulerPage` chunk |
| Playwright 真实链路 | 隔离 lite API + Vite 登录后，侧栏进入 `/scheduler`，创建 `Release audit` 并读回；点击“立即运行”后页面先见 attempt 0 `retry_wait`，后台领取后读回 attempt 0 `retried` 与 attempt 1 `running` |

真实浏览器验证证明的是“页面 → 租户 API → 数据库 → 后台 scheduler claim”同链路，不将尚未等待完成的真实模型调用冒充终态成功；终态、失败重试和通知隔离由数据库集成测试覆盖。

## 新鲜验证

| 验证 | 结果 |
|---|---|
| 后端关联回归 | `test_durable_scheduler.py`、`test_durable_scheduler_api.py`、`test_webhooks.py`、`test_multi_instance.py` 共 26/26 通过 |
| 目标 Ruff | scheduler/webhook/persistence/domain/main 及关联测试全部通过 |
| 目标 mypy | scheduler/webhook/persistence/domain/main 全部通过，0 项 |
| 全仓静态门禁 | Ruff `276 <= 286`；mypy `67 <= 74`，均低于 P0/P1 基线 |
| fresh migration | 空 SQLite 从初始版本升级到 `20260807_durable_scheduler (head)` |
| 表回读 | `sqlite_master` 返回 `scheduled_job_runs,scheduled_jobs`，`alembic_version=20260807_durable_scheduler` |
| 工作树 | 实现提交后 `git status --short` 无输出 |

Windows 中文路径下 `uv run --isolated` 曾在 Python site 初始化阶段触发 GBK 解码错误；验证改用 ASCII 临时虚拟环境并通过 `-S` 显式装载项目/测试依赖，未修改全局 Python，业务测试实际执行并通过。

## P2-A 实现提交

- `097033c`：增加持久任务运行模型与原子领取。
- `fc7ef3b`：增加租约恢复与有界重试。
- `33c49be`：接入数据库执行循环与租户 API。
- `379935a`：增加 Web 持久调度中心与手动运行。
- `5e5e0fb`：完成 Redis 所有者租约、终态通知回执和暂停重试边界。
- `76c996a`：恢复全部租户持久 Webhook 配置。

## 已知剩余风险

- 多实例部署必须配置 Redis；未配置时仍依赖数据库原子 claim 保证 run 唯一，但不具备 Redis job 级互斥。
- Webhook 当前在终态后顺序投递，每个目标超时 10 秒；任务终态不会被通知失败回滚，但大量慢 Webhook 后续应改为独立投递队列。
- 旧 JSON scheduler 的兼容读写方法仍在代码中，但主循环和 Web/API 已不再从它触发；最终发布审计需决定迁移删除窗口。
- Web 仍有 100 条存量 ESLint warning；P2 总收口必须按计划归零或形成逐项 owner/理由/失效日期豁免。
- P2-B Skill Package、P2-C 数据库 checkpoint 和 P2-D MCP 接口尚未完成，因此当前不能判定整个 Web/API 已达发布标准。
