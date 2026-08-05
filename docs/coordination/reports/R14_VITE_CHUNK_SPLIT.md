# R14 Vite Chunk Warning Root Cause And Split Evidence

> 日期：2026-07-06
> Owner：Codex
> 范围：`apps/web` Vite bundle warning 根因定位与最小拆包处理

## 1. 结论

R14 已通过路由级 `React.lazy` / `Suspense` 拆包清除 Vite `Some chunks are larger than 500 kB` warning。

本次没有提高 Vite `chunkSizeWarningLimit`，没有升级 Vite major，也没有改变业务路由语义。修复后 `npm run build` 退出码为 0，最大 JS chunk 为 `assets/index-C1uREjI3.js` 294.19 kB / gzip 96.09 kB，低于 500 kB warning 阈值。

## 2. 根因

R11 / R13 记录的旧构建状态显示，`npm run build` 可通过，但主 JS bundle 约 606 kB，并触发 Vite chunk size warning。

R14 复查 sourcemap 后确认主要来源不是单一业务 bug，而是 `App.tsx` 同步 import 了所有页面，导致以下内容被提前打入首屏主包：

- React Flow / canvas 相关依赖与 `CreativeStudioPage`
- settings / run console / editor / memory / open-source 等非首屏页面
- route 页面级业务组件与其依赖树

因此最小有效处理是页面路由级懒加载，而不是调高阈值掩盖 warning。

## 3. 变更

- `apps/web/src/App.tsx`
  - 将非登录页面改为 `lazy(() => import(...))`。
  - 用 `Suspense` 包裹登录后路由和 `/creative/canvas` 独立入口。
  - 增加轻量 `PageFallback`，只作为页面 chunk 加载态。

## 4. Build 证据

命令：

```powershell
npm run build
```

结果：

- 退出码：0
- Vite chunk warning：未出现
- 关键产物：
  - `assets/index-C1uREjI3.js`：294.19 kB / gzip 96.09 kB
  - `assets/style-DNRkz53j.js`：146.49 kB / gzip 47.93 kB
  - `assets/CreativeStudioPage-LD-5IVNL.js`：77.45 kB / gzip 22.51 kB
  - `assets/RunPage-Bm5HHSPO.js`：21.71 kB / gzip 6.12 kB
  - `assets/SettingsPage-CQ2PuY2Z.js`：20.61 kB / gzip 6.33 kB
  - `assets/ChatPage-DUZDy3ms.js`：7.55 kB / gzip 3.43 kB

`dist/assets` 复查的最大 JS 文件：

```text
index-C1uREjI3.js                288.94 KB
style-DNRkz53j.js                143.06 KB
CreativeStudioPage-LD-5IVNL.js    79.46 KB
RunPage-Bm5HHSPO.js               22.42 KB
SettingsPage-CQ2PuY2Z.js          21.62 KB
```

## 5. 验证

命令：

```powershell
npm run lint
npm run typecheck
node --test tests/chatStream.test.mjs
npm run build
$env:E2E_BASE_URL = 'http://127.0.0.1:3100'
$env:E2E_USERNAME = 'admin'
$env:E2E_PASSWORD = 'admin'
npx playwright test specs/full-flow.spec.ts --project=chromium
```

结果：

- `npm run lint`：退出码 0。
- `npm run typecheck`：退出码 0。
- `node --test tests/chatStream.test.mjs`：3 passed。
- `npm run build`：退出码 0，未出现 Vite chunk warning。
- `full-flow.spec.ts --project=chromium`：9 passed。

E2E 环境：

- API：`http://127.0.0.1:8000`
- Web：`http://127.0.0.1:3100`
- DB：`apps/api/r14-full-flow.db`

## 6. 边界

本包只处理 Vite chunk warning 的根因定位与最小拆包。

本包不处理：

- Vite / esbuild dev-build 工具链全量 `npm audit` 风险清零。
- 性能压测、真实首屏指标、CDN 缓存策略或生产监控。
- R4 目标环境演练。
- R5 PR 审查包组装。

## 7. Reviewer 关注点

- 确认本次是路由级拆包，不是调高 Vite warning 阈值。
- 确认 `/creative/canvas` 独立入口仍被 `Suspense` 覆盖，未破坏 full-flow。
- 确认 build warning 清零不被误写成正式发布或性能签字。
