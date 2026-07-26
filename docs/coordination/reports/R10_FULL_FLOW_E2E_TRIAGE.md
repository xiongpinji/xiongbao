# R10 full-flow E2E 补齐与差异归因

- 任务包：R10 full-flow E2E 补齐与差异归因
- 交付人：Codex
- 日期：2026-07-06
- 工作树：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent`
- 范围：`tests/e2e/specs/full-flow.spec.ts` 与本报告；不修复运行时代码，不替代 R1/R4/R5。

## 环境

- API：`http://127.0.0.1:8000`
- Web：`http://127.0.0.1:3100`
- E2E 账号：`E2E_USERNAME=admin` / `E2E_PASSWORD=admin`
- API 启动变量：
  - `PYTHONPATH=apps/api`
  - `XAGENT_DB__URL=sqlite+aiosqlite:///./r10-full-flow.db`
  - `XAGENT_CANVAS_SNAPSHOT=r10-canvas-snapshot.json`
  - `XAGENT_DEV_SEED_ADMIN=true`

## 变更

- 将首页导航断言从宽泛 `text=` 改为主导航 link 断言，消除 strict mode 多匹配。
- 将设置页“索引库”和“设置”断言收窄到 heading。
- 将短剧工厂 brief 控件从旧 `input[placeholder*=brief]` 改为当前 `textbox` 可访问名“短剧 brief”。
- 将短剧工厂生成按钮从宽泛“生成”改为“生成画布”，并验证按钮启用后点击。
- 将短剧工厂结果断言收窄到 React Flow wrapper 与“需求分析节点”，消除多个“未审核”节点造成的 strict mode 多匹配。
- 将对话运行按钮从旧文本按钮“运行”改为当前图标按钮 `title="运行 Agent"`；该用例仍未稳定通过，见下方归因。

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "首页加载"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "设置页索引库"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "智能体角色列表"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "后台任务可进入"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "短剧工厂生成草稿"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "设置页加载"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "响应含安全头"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "工作流创建执行"` | 1 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium --grep-invert "对话运行 agent"` | 8 passed |
| `npx playwright test specs/full-flow.spec.ts --project=chromium -g "对话运行 agent"` | 未通过；100s 内未出现“查看运行详情”，外层命令超时后清理 Playwright 残留 |

## 剩余失败归因

失败用例：`X-Agent 核心流程 › 对话运行 agent`

已排除：

- 登录失败：`POST /api/v1/auth/login` 返回 200。
- 按钮选择器漂移：已改为点击当前页面真实按钮 `title="运行 Agent"`。
- 后端入口不可达：API 日志显示 `POST /api/v1/stream/agents/run` 返回 200。

当前证据：

- 失败快照中主页面仍停留在用户消息与输入区，没有出现 bot 结果区或“查看运行详情”。
- Context 面板出现运行详情记录，但 Chat 主页面未设置完成态。
- 后端日志显示 SSE 请求 200，未看到可用于主页面完成态的后续结果证据。

判断：

- 这是 Chat SSE 完成事件 / 前端完成态处理的剩余阻断，不再是 full-flow selector 漂移。
- R10 不在本包内修改 `apps/web/src/pages/ChatPage.tsx` 或后端 streaming 实现，避免隐式扩 scope。

## 影响范围

- `tests/e2e/specs/full-flow.spec.ts` 不能整体宣称全绿。
- 当前可作为 PR 审查证据的是“除对话运行 agent 外 8/9 full-flow 用例通过”。
- 不能据此勾选“关键 full-flow E2E 全量通过”或正式商用发布门禁。

## 后续修复清单

1. 拆新任务修复 Chat SSE：当 `/api/v1/stream/agents/run` 返回 200 但没有 `done` 事件时，应抛错进入 `runAgent` fallback，或保证 SSE 始终发送带 `run_id` 的 done 事件。
2. 为 Chat SSE 完成态增加单元/组件测试，覆盖“正常 done”“无 done 关闭”“错误事件”三类分支。
3. 修复后复跑完整 `npx playwright test specs/full-flow.spec.ts --project=chromium`，再更新发布检查表证据。

