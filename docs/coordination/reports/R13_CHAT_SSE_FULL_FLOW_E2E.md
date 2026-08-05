# R13 Chat SSE 完成态与 full-flow 复绿记录

- 任务包：R13 Chat SSE 完成态 / 回退闭环修复并复绿 full-flow
- 交付人：Codex
- 日期：2026-07-06
- 工作树：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`

## 结论

- `ChatPage` 的 SSE 读取逻辑已拆为 `readAgentRunStream`，只有收到带 `run_id` 的 `done` 事件才视为流式运行成功。
- SSE 流自然结束但没有 `done` 时会抛出 `SSE stream ended before done event`，触发既有 `/api/v1/agents/run` fallback。
- `ChatPage` 主区渲染条件已纳入 `runId`，修复“右侧 Context 已同步 run id，但主区不显示查看运行详情”的 UI 断点。
- `tests/e2e/specs/full-flow.spec.ts --project=chromium` 已从 R10 的 8/9 提升到 9/9 通过。

## 变更文件

- `apps/web/src/api/chatStream.ts`
- `apps/web/src/pages/ChatPage.tsx`
- `apps/web/tests/chatStream.test.mjs`

## 关键诊断

R10 剩余失败并非 selector 漂移。R13 复验显示：

- API 8000 收到 `POST /api/v1/stream/agents/run` 并返回 200。
- `syncRunTask` 已把 run id 同步到右侧 Context。
- 主内容区仍不出现“查看运行详情”，因为 Bot 消息容器的渲染条件缺少 `runId`。

因此最小修复为：

1. 把 SSE 解析和 done 完成态抽成可测试 helper。
2. 对无 `done` 的流结束显式失败，让普通 run fallback 生效。
3. 让 `runId` 单独存在时也渲染主区运行详情入口。

## 验证命令

```powershell
cd apps/web
node --test tests/chatStream.test.mjs
npm run lint
npm run typecheck
npm run build
```

```powershell
cd tests/e2e
$env:E2E_BASE_URL='http://127.0.0.1:3100'
$env:E2E_USERNAME='admin'
$env:E2E_PASSWORD='admin'
npx playwright test specs/full-flow.spec.ts --project=chromium -g "对话运行 agent"
npx playwright test specs/full-flow.spec.ts --project=chromium
```

## 验证结果

- `node --test tests/chatStream.test.mjs`：3 passed。
- `npm run lint`：通过。
- `npm run typecheck`：通过。
- `npm run build`：通过；仍有既有 Vite chunk warning，JS bundle 为 606.82 kB / gzip 189.30 kB。
- `对话运行 agent` 单例：1 passed。
- 完整 `full-flow.spec.ts`：9 passed。

## 边界与剩余风险

- 本包只修 Chat SSE 完成态 / fallback / 主区详情入口，不处理 R14 Vite chunk warning。
- 本包证据来自本地 API 8000 + 当前仓库 Web 3100 + lite admin 账号，不替代 R4 目标环境演练。
- 本包不宣称正式商用可交付；R4 目标环境演练与 R5 PR 审查包仍需总调度闭环。
