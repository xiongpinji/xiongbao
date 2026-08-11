# Web/API 发布硬化任务板

## Board Meta

- 总目标：X-Agent Web/API 达到可复现发布标准，并补齐 Codex/Hermes 关键产品闭环。
- 当前阶段：R3-B 可靠性缺陷修复已开始；先修复 Chat 截断响应假成功与隔离 file_write 180 秒硬超时，再进入定向 Live 验证。
- 设计源：`docs/superpowers/specs/2026-08-11-xagent-r3-model-reliability-design.md`。
- R3 计划：`docs/superpowers/plans/2026-08-11-xagent-r3-model-reliability.md`。
- P0 计划：`docs/superpowers/plans/2026-08-07-webapi-p0-release-foundation.md`。
- P2 计划：`docs/superpowers/plans/2026-08-07-webapi-p2-hermes-durable-autonomy.md`。
- 当前分支：`feature/webapi-r2-staging-readiness`。
- 当前 worktree：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\webapi-release-hardening`。
- 排除范围：短剧业务链路、Tauri 桌面端、多机 HA、E2B 和客户现场演练。
- Owner：Codex。
- 最后更新时间：2026-08-11。

## In Progress

- [R3-B] Chat 截断终态与隔离 file_write 超时边界 | 状态：CLAIMED | 根因已由 R3-A raw、数据库和源码调用链确认；按 `docs/superpowers/specs/2026-08-11-xagent-r3b-reliability-repair-design.md` 先红后绿，独立审查前不重建容器或重跑完整批次。
- [R3-A] 真实 Ollama 可靠性基线 | 状态：PARTIAL | 批次 `20260811T064937Z-2ec342` 完整记录 50/50：Chat 29/30、P95 9.139 秒，但 `chat-001` 为 succeeded + 截断答案的假成功；Scheduler 10/10、P95 40.381 秒且全部暂停；file_write 5/10、P95 180.539 秒，另 5 条约 180 秒 timeout/missing_artifact，均 fail-closed 且清理成功。租户隔离通过，MockLLM/forbidden/cleanup failure 均为 0。下一门是先修复 Chat 假成功与 file_write 可靠性，不直接重跑。证据：`docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md`。

## Ready

- 暂无。

## Queued

- 暂无。

## Done

- [R2-A] R2 运行入口、配置门禁与任务板初始化 | 状态：DONE | 证据：最终候选 `bad1aa8` 的 preflight、Compose config、CI Web/API 后端范围入口、镜像内 `739 passed / 8 skipped`、release contracts `40/40`、Ruff/mypy 精确基线、许可证与版本门均通过；核心、扩展及受保护服务边界明确。详见 `docs/coordination/reports/WEB_API_R2_STAGING_TRIAL_EVIDENCE.md`。
- [R2-B] R2 核心六服务 Full Compose 试运行 | 状态：DONE | 证据：最终 headed Chromium 同轮 `6/6 passed`、workers=1、retries=0、总用时 2.0 分钟；真实 `qwen3:4b` Chat、Run/reload、scheduler exact result、完整 Skill ZIP、真实 file_write worktree/patch、第二租户隔离全部通过，console/pageerror/短剧媒体请求均 0；六张 1280×720 脱敏截图已复核。
- [R2-C] R2 重启、故障恢复与持久化复验 | 状态：DONE | 证据：API/Worker restart、Nginx Docker DNS/WS 恢复、Worker pause/unpause、Redis degraded/恢复、无 `-v` down/up、四卷与全部业务锚点复读均通过；无重复终态、跨 loop 或 terminal checkpoint 错误。
- [R2-D] R2 MCP 与 observability 可选服务验收 | 状态：DONE | 证据：Platform MCP 15 tools、认证与租户隔离、Prometheus 实时 metrics target、Grafana datasource/dashboard/query、只读 provisioning mount 均通过；最终服务健康且 MockLLM 为 0。
- [R2-E] R2 备份与全新隔离 project 恢复演练 | 状态：DONE | 证据：PostgreSQL/Qdrant/Redis/xagentdata 四件仓库外备份在 fresh project/端口/network/volumes 恢复；表计数、Qdrant 27 points、Skill 文件和 Development Patch 锚点一致，真实 restore run 精确 `R2-RESTORE-OK`；restore 已无 `-v` down，卷与备份保留。

- [R1] Web/API 发布级全量审计与 Release gate 实跑 | 状态：DONE | 证据：最终 API 镜像全量测试 `720 passed / 15 skipped`，Web `25/25`，类型/构建/精确静态门禁、许可证、版本、fresh migration、镜像健康和 Git 运行时均通过；真实浏览器完成 run、证据、调度持久化、Skill 持久化、会话点击/刷新恢复及 1037px 运行台视觉复验，控制台 0/0；详见 `docs/coordination/reports/WEB_API_R1_RELEASE_AUDIT_EVIDENCE.md`。
- [P2-D] MCP 会话、运行、审批与事件接口 | 状态：DONE | 证据：15 个租户受控 MCP 工具、统一 Principal/RBAC/tenant/audit、精确确认的取消与审批、事件/技能包脱敏、MCP run 持久同链、非回环 HTTP 强制 token 均成立；MCP 合同 18/18、Runtime/worker 37/37、目标 Ruff/mypy 0、全仓 Ruff `262 <= 286`、mypy `65 <= 74`、fresh migration、真实 MCP 协议工具发现/会话读取和 401 鉴权通过；详见 `docs/coordination/reports/WEB_API_P2D_PLATFORM_MCP_EVIDENCE.md`。
- [P2-C] 数据库 checkpoint、恢复/回滚与 Web 时间线 | 状态：DONE | 证据：数据库 checkpoint、脱敏与 workspace 相对路径、每 5 步/取消落库、租户会话恢复、父子 run 谱系、原子重复恢复阻断、开发任务约束的 commit/patch 回滚和 Web 时间线均成立；后端关联 11/11、Runtime 23/23、Web 21/21、全仓 Ruff `262 <= 286`、mypy `65 <= 74`、fresh migration 和真实 Playwright 恢复同链通过；详见 `docs/coordination/reports/WEB_API_P2C_CHECKPOINT_RECOVERY_EVIDENCE.md`。
- [P2-B] 完整 Skill Package 导入、存储与安全门禁 | 状态：DONE | 证据：数据库 package 事实源、完整 SKILL.md/references/scripts/assets、ZIP/目录大小与路径门禁、租户 API、完整正文运行时、Web manifest/hash 和 commit 失败补偿均成立；后端关联 45 项通过/1 项环境权限跳过、Web 19/19、目标 Ruff/mypy 0、全仓 Ruff `271 <= 286`、mypy `65 <= 74`、fresh migration 和真实 Playwright 同链路通过；详见 `docs/coordination/reports/WEB_API_P2B_SKILL_PACKAGE_EVIDENCE.md`。
- [P2-A] durable scheduler、运行历史、重试恢复与 Web 页面 | 状态：DONE | 证据：数据库 Job/Run、原子 claim、Redis 所有者租约、启动恢复、有界退避、暂停边界、终态 Webhook 独立回执、多租户重启恢复、租户 API 和 Web 控制台均已成立；后端关联 26/26、Web 17/17、目标 Ruff/mypy 0、fresh migration、typecheck/build 和真实 Playwright 同链路通过；详见 `docs/coordination/reports/WEB_API_P2A_DURABLE_SCHEDULER_EVIDENCE.md`。
- [P1-B] review/apply API 与 Web 开发任务控制台 | 状态：DONE | 证据：相关后端 31/31、Web 14/14、lint 0/100、typecheck/build、fresh migration 和真实 Playwright 导航验证通过；浏览器发现的侧栏入口缺失已修复；详见 `docs/coordination/reports/WEB_API_P1_DEVELOPMENT_TASK_LOOP_EVIDENCE.md`。
- [P1-A] worktree 结果持久模型、Git 生命周期与审查 API | 状态：DONE | 证据：完成 tenant-scoped 持久记录、成功结果 commit/worktree/branch/full patch 保留、approve/reject/apply/conflict/expire/cancel 状态链；API 实测租户隔离、显式 task ID 确认、路径脱敏与审计，相关后端测试 18/18 通过。
- [P0-A] 流式并发工具执行正确性 | 状态：DONE | 证据：新增测试先失败于两个 `_tool_success` `UnboundLocalError`，修复后定向测试 1/1、编排回归 11/11 通过，`F823` 为 0；双工具真实结果为 `a`/`b`，最终统计为 2 次调用、成功率 100%。
- [P0-B] 关键 Ruff 阻断与静态质量基线 | 状态：DONE | 证据：基线测试先因脚本不存在失败；修复后相关测试 12/12、关键规则 `F821,F822,F823,B023` 通过，完整 Ruff `279 <= 286`、mypy `73 <= 74`；CI 已移除静态检查 `|| true` 并通过 YAML 解析。
- [P0-C] Web 测试入口与排除模块边界 | 状态：DONE | 证据：导航测试先因 `taskId=creative` 失败；修复后默认 `npm test` 自动执行 2 个文件共 11 项，lint `0 error / 100 warnings`，typecheck/build 通过；短剧、画布、剪辑旧路由统一进入排除说明页，构建无 `CreativeStudioPage`/`EditorPage` chunk，CI 已加入 Web 单元测试。
- [P0-D] Web/API 版本事实源与 CI 后发布 | 状态：DONE | 证据：版本测试先因脚本不存在失败；API/Web/README 与 `v1.0.0` 一致性测试通过，Release job 的 `needs` 已验证覆盖 9 个 Web/API gate；文档明确短剧/桌面排除且现有旧标签不得移动或复用。
- [P0-E] P0 发布证据与阶段审计 | 状态：DONE | 证据：后端 13/13、Web 11/11、关键 Ruff 0、完整 Ruff `279 <= 286`、mypy `73 <= 74`、lint `0/100`、typecheck/build、Git/CI/产物一致性全部通过；详见 `docs/coordination/reports/WEB_API_P0_RELEASE_FOUNDATION_EVIDENCE.md`。

## 基线证据

- 后端编排测试：11/11 通过。
- Web 单元测试：默认脚本自动发现 2 个测试文件，共 11/11 通过。
- Web lint：0 error / 100 warnings。
- Web typecheck：通过。
- Web build：通过。
- Ruff：门禁上限 286 项，P0-B 新鲜结果 279 项；关键集合 `F821,F822,F823,B023` 为 0。
- mypy：门禁上限 74 项，P0-B 新鲜结果 73 项。
- `npm ci`：6 个开发依赖漏洞（3 moderate / 3 high），另行纳入依赖审计，不用 `--force` 自动升级。
- P2-A 新鲜结果：后端关联 26/26、Web 17/17、Ruff `276 <= 286`、mypy `67 <= 74`、lint 0 error / 100 warnings、fresh migration 到 `20260807_durable_scheduler`。
- P2-B 新鲜结果：后端关联 45 项通过/1 项环境权限跳过、Web 19/19、Ruff `271 <= 286`、mypy `65 <= 74`、lint 0 error / 100 warnings、fresh migration 到 `20260807_skill_packages`。
- P2-C 新鲜结果：后端关联 11/11、Runtime 23/23、Web 21/21、Ruff `262 <= 286`、mypy `65 <= 74`、lint 0 error / 100 warnings、fresh migration 到 `20260807_checkpoints`，真实恢复 run 完成。
- P2-D 新鲜结果：MCP 定向合同 18/18、Runtime/worker 37/37、目标 Ruff/mypy 0、全仓 Ruff `262 <= 286`、mypy `65 <= 74`；fresh migration 后真实 MCP Streamable HTTP 列出 15 个工具、读取同租户会话，无凭证请求返回 401。
- R1 最终结果：发布镜像后端 `720 passed / 15 skipped`；Web `25/25`、typecheck/build 通过；API/Web 精确质量指纹通过；许可证、版本、fresh migration、镜像健康、容器 Git 和真实浏览器主链通过。生产依赖仅保留不可达的 React Router RSC 公告限期例外。

## 状态规则

- 只有先记录失败证据、再完成最小修复并通过验证，任务才能从 CLAIMED 转 REVIEW。
- REVIEW 必须包含精确命令、结果、改动文件和剩余风险。
- 不以短剧或桌面测试作为本阶段完成条件，也不得把它们写成已发布能力。
- P1/P2 任务在各自实现计划落盘前不得转 CLAIMED。
