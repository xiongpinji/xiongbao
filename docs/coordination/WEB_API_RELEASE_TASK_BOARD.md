# Web/API 发布硬化任务板

## Board Meta

- 总目标：X-Agent Web/API 达到可复现发布标准，并补齐 Codex/Hermes 关键产品闭环。
- 当前阶段：R2 本地 Full Compose 核心栈试运行，R2-A 等待复核。
- 设计源：`docs/superpowers/specs/2026-08-07-xagent-webapi-r2-local-full-compose-design.md`。
- P0 计划：`docs/superpowers/plans/2026-08-07-webapi-p0-release-foundation.md`。
- P2 计划：`docs/superpowers/plans/2026-08-07-webapi-p2-hermes-durable-autonomy.md`。
- 当前分支：`feature/webapi-r2-staging-readiness`。
- 当前 worktree：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\webapi-release-hardening`。
- 排除范围：短剧业务链路、Tauri 桌面端、多机 HA、E2B 和客户现场演练。
- Owner：Codex。
- 最后更新时间：2026-08-09。

## In Progress

- [R2-A] R2 运行入口、配置门禁与任务板初始化 | 状态：REVIEW | 证据：2026-08-09 在 `feature/webapi-r2-staging-readiness` / `306bd3a1a40423dddcd4301dd04887b20c1389e3` 从 fresh R2 resources 启动核心六服务；Docker `client=29.5.3 server=29.5.3`，Compose `v5.1.4`，宿主机 Ollama 有 `qwen3:4b`。`pwsh -NoProfile -File scripts/r2-preflight.ps1` 7/7 ok；启动前 `xagent-r2` 容器、volume、network 均为空。`apps/web` 的 `npm ci` 与 `npm run build` 退出 0；`docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local build api worker web` 退出 0。仅启动 `postgres redis qdrant api worker web`，六服务均 running/healthy，端口为 `127.0.0.1:18000/18080/15432/16379/16333/16334`；镜像 ID：api `sha256:650b4d956a2ab61180514bb62a020385a9e0ea64208734359d771fc315f807e3`，worker `sha256:61ca86f45aef63b22c857f2349cd62d580922aedc442da8bc19829536a99cca6`，web `sha256:a4b6d5cab532397cff3b11206f00b1b82e68ef296467629bca857bdc2d597a32`，postgres `sha256:e013e867e712fec275706a6c51c966f0bb0c93cfa8f51000f85a15f9865a28cb`，redis `sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99`，qdrant `sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c`。`python -m alembic current` 为 `20260807_checkpoints (head)`；`/health` 为 `ok`，`/health/ready` 为 `ready`，`/health/deep` 为 `healthy` 且 database/redis/qdrant 均 healthy；`celery -A xagent.worker.celery_app inspect ping --timeout=5` 返回 pong。隔离账号 `r2-reviewer` / tenant `r2-trial` 注册成功，`POST /api/v1/agents/run` 返回 run_id `aa62c3302b96402e8a46b57409b5de96` 且 final answer 非空；容器内配置为 `LiteLLMClient`、`ollama_base_url=http://host.docker.internal:11434`、`effective_model=ollama/qwen3:4b`，API/worker 日志有 `ollama_warmup_succeeded model=qwen3:4b route=ollama`，API run 日志有 `LiteLLM completion() model= qwen3:4b; provider = ollama`，未出现 MockLLM。按 env secret 值对 30 分钟服务日志复扫，4 个 secret 值 0 命中；`aicg-postgres` 与 `aicg-minio` 仍为原容器 ID `3af4cf4c653d` / `07e3c2aef1a1` 且 healthy，未被本任务重建。

## Ready

- 暂无。

## Queued

- [R2-B] R2 核心六服务 full Compose 试运行 | 状态：PENDING | 证据：待执行；核心服务范围为 `postgres redis qdrant api worker web`；浏览器验收使用 `http://127.0.0.1:18080`，脱敏截图提交到 `output/playwright/`。
- [R2-C] R2 重启、故障恢复与持久化复验 | 状态：PENDING | 证据：待执行；不得使用原始证据目录。
- [R2-D] R2 MCP 与 observability 可选服务验收 | 状态：PENDING | 证据：待执行；仅在核心服务通过后启用 `mcp` 与 `observability`，脱敏截图提交到 `output/playwright/`。

## Done

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
