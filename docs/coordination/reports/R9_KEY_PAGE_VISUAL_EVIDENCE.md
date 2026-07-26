# R9 关键页面截图/验收记录

> 日期：2026-07-06
> Owner：Codex
> 范围：登录、对话/工作台、工作流、Run Console、设置页索引库的页面级验收证据。
> 结论：本记录仅证明关键页面可打开、关键元素可见并已生成本地截图；不等同远端 CI、目标环境演练或正式发布签字。

## 1. 证据目录

截图输出目录：`docs/coordination/reports/evidence/r9-key-pages/`

| 文件 | 页面 | 验收点 |
|---|---|---|
| `01-login.png` | 登录页 | 标题 `熊宝智能体系统` 可见 |
| `02-chat-workbench.png` | 对话 / 工作台 | 标题 `对话` 与空态问题 `今天想要构建什么？` 可见 |
| `03-workflow.png` | 工作流 | 标题 `工作流` 与 `创建并执行` 按钮可见 |
| `04-run-console.png` | Run Console | `Run Console` 与 `验证 · 风险 · 恢复` 可见 |
| `05-settings-index.png` | 设置页索引库 | 标题 `索引库`、`知识库`、`开源发现` 可见 |

## 2. 执行命令

```powershell
cd apps/api
$env:PYTHONPATH = (Get-Location).Path
$env:XAGENT_DB__URL = "sqlite+aiosqlite:///./r9-visual-evidence.db"
$env:XAGENT_CANVAS_SNAPSHOT = "r9-canvas-snapshot.json"
$env:XAGENT_DEV_SEED_ADMIN = "true"
xagent serve --host 127.0.0.1 --port 8000
```

```powershell
cd apps/web
$env:XAGENT_DEV_API_TARGET = "http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 3100
```

```powershell
cd tests/e2e
$env:E2E_BASE_URL = "http://127.0.0.1:3100"
npx playwright test specs/r9-visual-evidence.spec.ts --project=chromium
```

## 3. 与发布检查表映射

- 登录页：覆盖登录入口和 lite/dev 本地账号路径的可见性记录。
- 对话 / 工作台：覆盖首屏工作台和对话入口。
- 工作流：覆盖专业模式中的工作流入口与创建按钮。
- Run Console：覆盖运行详情页和恢复/验证面板入口。
- 设置页索引库：覆盖设置页中知识库 / 开源发现收口入口。

## 4. 执行结果

- `npx playwright test specs/r9-visual-evidence.spec.ts --project=chromium`：`1 passed`
- 截图尺寸检查：5 张 PNG 均为 `1440x1000`

| 文件 | 尺寸 | 字节数 |
|---|---:|---:|
| `01-login.png` | `1440x1000` | 344382 |
| `02-chat-workbench.png` | `1440x1000` | 582994 |
| `03-workflow.png` | `1440x1000` | 375407 |
| `04-run-console.png` | `1440x1000` | 392526 |
| `05-settings-index.png` | `1440x1000` | 325808 |

## 5. 剩余边界

- 本记录不验证真实目标环境。
- 本记录不验证远端 CI。
- 本记录不验证长任务模型质量、性能或压测。
- 本记录不替代 R4 环境演练与 R5 PR 审查包。
