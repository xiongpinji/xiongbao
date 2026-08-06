# Web/API 发布硬化任务板

## Board Meta

- 总目标：X-Agent Web/API 达到可复现发布标准，并补齐 Codex/Hermes 关键产品闭环。
- 当前阶段：P0 发布可信基线。
- 设计源：`docs/superpowers/specs/2026-08-07-xagent-webapi-competitive-parity-design.md`。
- P0 计划：`docs/superpowers/plans/2026-08-07-webapi-p0-release-foundation.md`。
- 当前分支：`feature/webapi-release-hardening`。
- 当前 worktree：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\webapi-release-hardening`。
- 排除范围：短剧业务链路、Tauri 桌面端、多机 HA、E2B 和客户现场演练。
- Owner：Codex。
- 最后更新时间：2026-08-07。

## In Progress

- [P0-E] P0 发布证据与阶段审计 | 状态：CLAIMED | Owner：Codex | 依赖：P0-A,P0-B,P0-C,P0-D | 验收：P0 相关后端测试、前端 test/lint/typecheck/build、静态门禁和 workflow 结构检查全部有新鲜证据。

## Ready

- 暂无；P0-E 审计通过后再将 P1-A 转 READY。

## Queued

- [P1-A] worktree 结果持久模型与 Git 生命周期 | 状态：QUEUED | 依赖：P0-E。
- [P1-B] review/apply API 与 Web 开发任务控制台 | 状态：QUEUED | 依赖：P1-A。
- [P2-A] durable scheduler、运行历史、重试恢复与 Web 页面 | 状态：QUEUED | 依赖：P1-B。
- [P2-B] 完整 Skill Package 导入、存储与安全门禁 | 状态：QUEUED | 依赖：P2-A。
- [P2-C] 数据库 checkpoint、恢复/回滚与 Web 时间线 | 状态：QUEUED | 依赖：P2-B。
- [P2-D] MCP 会话、运行、审批与事件接口 | 状态：QUEUED | 依赖：P2-C。
- [R1] Web/API 发布级全量审计与 Release gate 实跑 | 状态：QUEUED | 依赖：P2-D。

## Done

- [P0-A] 流式并发工具执行正确性 | 状态：DONE | 证据：新增测试先失败于两个 `_tool_success` `UnboundLocalError`，修复后定向测试 1/1、编排回归 11/11 通过，`F823` 为 0；双工具真实结果为 `a`/`b`，最终统计为 2 次调用、成功率 100%。
- [P0-B] 关键 Ruff 阻断与静态质量基线 | 状态：DONE | 证据：基线测试先因脚本不存在失败；修复后相关测试 12/12、关键规则 `F821,F822,F823,B023` 通过，完整 Ruff `279 <= 286`、mypy `73 <= 74`；CI 已移除静态检查 `|| true` 并通过 YAML 解析。
- [P0-C] Web 测试入口与排除模块边界 | 状态：DONE | 证据：导航测试先因 `taskId=creative` 失败；修复后默认 `npm test` 自动执行 2 个文件共 11 项，lint `0 error / 100 warnings`，typecheck/build 通过；短剧、画布、剪辑旧路由统一进入排除说明页，构建无 `CreativeStudioPage`/`EditorPage` chunk，CI 已加入 Web 单元测试。
- [P0-D] Web/API 版本事实源与 CI 后发布 | 状态：DONE | 证据：版本测试先因脚本不存在失败；API/Web/README 与 `v1.0.0` 一致性测试通过，Release job 的 `needs` 已验证覆盖 9 个 Web/API gate；文档明确短剧/桌面排除且现有旧标签不得移动或复用。

## 基线证据

- 后端编排测试：11/11 通过。
- Web 单元测试：默认脚本自动发现 2 个测试文件，共 11/11 通过。
- Web lint：0 error / 100 warnings。
- Web typecheck：通过。
- Web build：通过。
- Ruff：门禁上限 286 项，P0-B 新鲜结果 279 项；关键集合 `F821,F822,F823,B023` 为 0。
- mypy：门禁上限 74 项，P0-B 新鲜结果 73 项。
- `npm ci`：6 个开发依赖漏洞（3 moderate / 3 high），另行纳入依赖审计，不用 `--force` 自动升级。

## 状态规则

- 只有先记录失败证据、再完成最小修复并通过验证，任务才能从 CLAIMED 转 REVIEW。
- REVIEW 必须包含精确命令、结果、改动文件和剩余风险。
- 不以短剧或桌面测试作为本阶段完成条件，也不得把它们写成已发布能力。
- P1/P2 任务在各自实现计划落盘前不得转 CLAIMED。
