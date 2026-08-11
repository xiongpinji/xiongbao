# X-Agent R3-B 可靠性缺陷修复设计

> 日期：2026-08-11
>
> 状态：CLAIMED
>
> 基线：`feature/webapi-r2-staging-readiness` / `b8cecee`

## 1. 目标

修复 R3-A 批次 `20260811T064937Z-2ec342` 暴露的两个产品边界：

1. 无工具 Chat 把非空但被 token 上限截断的响应持久化为成功；
2. 隔离 `file_write` 在 180 秒被产品主动取消，早于 240 秒 SLO。

本任务不改变模型、provider、提示词、工具权限或 R3 样本判定标准。

## 2. Chat 合同

- 首次响应为空、`finish_reason=length` 或 completion tokens 达到请求上限时，只允许一次受控恢复。
- 截断恢复使用 1024 tokens；普通空响应保持 512 tokens 恢复预算。
- 恢复响应再次为空或仍被截断时，AgentRun 必须以明确错误失败，不得发出 final/done 或持久化为 succeeded。
- 正常非空且未触及上限的响应保持现有单次成功路径。

## 3. 隔离 file_write 超时合同

- 普通并行任务继续使用 180 秒超时。
- 只有建立真实 worktree 且 capability 精确为 `[file_write]` 的严格开发任务使用 270 秒 Agent 执行预算。
- 270 秒高于 240 秒统计 SLO，避免产品在 SLO 前截断；同时给现有 300 秒黑盒请求保留终态持久化、Git finalize 和 HTTP 返回余量。
- 超时仍保持现有 fail-closed、DB timeout、worktree/branch/patch 清理合同。

## 4. 验证顺序

1. 红灯：非空截断首答当前不会恢复；截断恢复当前会伪成功。
2. 绿灯：Chat 有界恢复与二次截断失败。
3. 红灯：严格 `file_write` 当前仍向 `asyncio.wait_for` 传 180 秒。
4. 绿灯：严格任务 270 秒、普通任务 180 秒，错误文本使用实际预算。
5. 运行 orchestration、runtime、parallel/development-task 回归及静态检查。
6. 独立审查通过前，不重建容器、不运行真实模型、不重跑 50 样本。

## 5. 排除范围

短剧/媒体、Tauri、多机 HA、E2B、付费 provider、远程 push/tag/release 和生产部署均不在本任务范围。
