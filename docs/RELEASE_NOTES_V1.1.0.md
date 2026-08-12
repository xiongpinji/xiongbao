# X-Agent v1.1.0 Release Notes

> 候选冻结：2026-08-12。
> 当前仅为本地 Web/API 发布候选；远端 CI、`v1.1.0` tag、GitHub Release 和目标环境签字尚未完成。
> 状态口径以 `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` 为唯一事实源。

## 版本定位

`v1.1.0` 是 `v1.0.0` 之后的向后兼容功能版本。提交区间包含 27 个 `feat`，未发现
`BREAKING CHANGE` 或 Conventional Commit 的 breaking 标记，因此按 SemVer 提升 MINOR，
不复用也不移动现有 `v1.0.0` 标签。

## 新增能力

- 开发任务闭环：租户隔离的 worktree、commit、完整 patch、审查、批准、拒绝、应用、冲突和清理状态链。
- 持久调度：数据库 Job/Run、原子领取、Redis 租约、重试恢复、终态通知及 Web 调度中心。
- Skill Package：安全导入完整 `SKILL.md`、references、scripts、assets，支持租户隔离存储、清单和正文运行时。
- Checkpoint 与恢复：数据库检查点、会话恢复、父子 run 谱系、受控回滚和 Web 时间线。
- Platform MCP：扩展至 15 个租户受控工具，覆盖会话、运行、审批、事件和技能包读取。
- Web/API Chat：增加无工具对话分路，保留真实模型输出并对空响应、截断响应和失败终态 fail-closed。
- 运维与可观测：R2 Compose 核心栈、动态 Docker DNS/精确 WebSocket 代理、Prometheus/Grafana、备份与隔离恢复演练。

## 可靠性与安全硬化

- file_write 开发任务要求真实工具调用、非空 diff 和受控路径，拒绝 `..`、外部绝对路径、`.git` 与符号链接逃逸。
- AgentRun、SSE、API、Celery 和调度终态统一，失败不再伪装为 `final`、`done` 或 `succeeded`。
- 修复 Worker 跨 event loop 数据库连接复用、Redis 深度健康检查超时、Prometheus 指标缓存和技能跨租户去重。
- 镜像发布等待版本一致性与七个运行门禁全部通过后才允许推送 GHCR，避免错误 tag 或未完成门禁提前覆盖 `latest`。

## 候选质量证据

- R3 不可变真实模型批次 `20260811T230626Z-f9a73d`：Chat 30/30、Scheduler 10/10、file_write 10/10。
- P95：Chat 8.152 秒、Scheduler 38.346 秒、file_write 177.452 秒；假成功、MockLLM、forbidden、租户泄漏和清理失败均为 0。
- R2 Full Compose 同轮 headed Chromium 6/6；重启、Redis 降级恢复、无 `-v` down/up、MCP、Prometheus/Grafana 和隔离恢复演练均已本地通过。
- 当前 Web/API 后端发布范围、R2/R3 release contracts、Web test/typecheck/build、Ruff/mypy 精确基线均已本地复验。
- 本节只证明本地候选；Hosted CI 和正式 Release 证据必须绑定后续远端候选 SHA。

## 发布范围外

- 短剧业务链路（独立项目稳定后再接入）。
- Tauri 桌面端。
- 多机 HA、E2B 云沙箱、付费 provider 和客户生产现场。
- SaaS 级容量或与 Codex/Hermes 全能力永久等价的承诺。

## 已知边界

- R3 file_write 的 parallel API 暂不直接暴露内部工具事件计数；真实工具使用由 required-first-tool 门、worktree、commit、diff、patch 和清理证据共同证明。
- 本地 `qwen3:4b` 可靠性数据只代表冻结批次和当前机器，不构成跨机器或生产 SLA。
- 私有仓库当前未配置 master 分支保护；正式远端操作必须遵守候选分支 → CI → PR/merge → master CI → tag 的人工门禁顺序。

## 升级与回滚

升级和回滚按 `docs/RELEASE_RUNBOOK_V1.md` 执行。发布前必须完成数据库备份、
`alembic upgrade head`、目标环境 smoke/E2E、镜像 digest 记录和回滚负责人签字；
失败时回退到不可变 `v1.0.0` 与对应数据备份，不移动任何既有标签。
