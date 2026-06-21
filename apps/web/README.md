# X-Agent Web

React 18 + Vite + TypeScript + Tailwind + Zustand + React Query 工作台。

## 开发

```bash
npm install
npm run dev      # http://localhost:3000（代理 /api -> :8000 后端）
npm run build    # 产物 dist/（供 Tauri 桌面壳加载）
npm run typecheck
```

## 页面

| 路由 | 功能 |
|---|---|
| `/chat` | 对话（运行 agent，展示最终回答 + 事件序列） |
| `/agents` | 智能体角色列表 |
| `/workflows` | 工作流创建/执行 + 结构化视图/timeline |
| `/creative` | 短剧工厂：一句话→草稿→React Flow 节点画布→审核 |
| `/open-source` | 开源候选发现 + 统一评分 |
| `/memory` | 知识库写入/语义检索 |
| `/settings` | 访问 token 设置 |

## 通信

- REST：axios，`/api/v1`，请求拦截注入 `Authorization: Bearer`
- 代理：Vite dev 把 `/api` `/ws` 转发到 `:8000` 后端
- lite 模式后端允许匿名；full 模式需在设置页填 token
