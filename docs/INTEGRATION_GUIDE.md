# 真实接入指南

> 本文档说明各"接口就绪"能力如何配置真实 key/运行时启用。
> 未配置时均走降级实现（Null/stub/内存），不影响核心流程。

## 1. 媒体生成（图像 + 视频）

### 图像：gpt-image-2 / DALL·E 3（OpenAI 兼容）

```bash
# .env
XAGENT_MEDIA__DEFAULT_IMAGE_PROVIDER=openai
XAGENT_MEDIA__OPENAI_IMAGE_API_KEY=sk-your-key
XAGENT_MEDIA__OPENAI_IMAGE_MODEL=gpt-image-2
# 可选：指向代理
# XAGENT_MEDIA__OPENAI_IMAGE_BASE_URL=https://api.openai.com/v1
```

验证：
```bash
curl -X POST localhost:8000/api/v1/creative-studio/media/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"kind":"image","prompt":"夕阳下的城市天际线","mode":"text_to_image","wait":true}'
```

### 视频：可灵 Kling

```bash
# .env
XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER=kling
XAGENT_MEDIA__KLING_API_KEY=your-kling-key
XAGENT_MEDIA__KLING_SUBMIT_URL=https://api.klingai.com/v1/videos/text2video
XAGENT_MEDIA__KLING_POLL_URL=https://api.klingai.com/v1/videos/{task_id}
```

### 视频：即梦 Jimeng

```bash
XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER=jimeng
XAGENT_MEDIA__JIMENG_API_KEY=your-jimeng-key
XAGENT_MEDIA__JIMENG_SUBMIT_URL=https://visual.volcengineapi.com/v1/videos/generate
XAGENT_MEDIA__JIMENG_POLL_URL=https://visual.volcengineapi.com/v1/videos/{task_id}
```

### 视频：通用任务式（对接任意 API）

```bash
XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER=generic
XAGENT_MEDIA__GENERIC_VIDEO_SUBMIT_URL=https://your-api.com/submit
XAGENT_MEDIA__GENERIC_VIDEO_POLL_URL=https://your-api.com/status/{task_id}
XAGENT_MEDIA__GENERIC_VIDEO_API_KEY=your-key
XAGENT_MEDIA__GENERIC_VIDEO_MODEL=your-model
```

详见 `docs/CREATIVE_STUDIO_MEDIA.md`。

---

## 2. Keycloak SSO（企业 OIDC）

### 部署 Keycloak

```bash
# compose 已含 langfuse，Keycloak 需单独起
docker run -d --name keycloak -p 8080:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:?set KEYCLOAK_ADMIN_PASSWORD}" \
  quay.io/keycloak/keycloak:latest start-dev
```

### 导入 realm

```bash
# 用 deploy/keycloak/xagent-realm.json 导入
# Keycloak UI: http://localhost:8080 → Administration → Import
```

realm 预设了：
- 角色：admin / member / viewer
- 客户端：xagent-api（OIDC）
- 用户：不再预设默认管理员；请在 Keycloak 中显式创建管理员并分配 admin 角色

### 配置后端

```bash
# .env
XAGENT_SECURITY__OIDC_JWKS_URL=http://localhost:8080/realms/xagent/protocol/openid-connect/certs
XAGENT_SECURITY__OIDC_ISSUER=xagent-api
```

配置后，Bearer token 走 RS256/JWKS 验签（Keycloak realm_access.roles 映射为 X-Agent 角色）。

---

## 3. MCP 真实工具接入

### 配置 MCP server

```bash
# .env（JSON 数组格式）
XAGENT_MCP__SERVERS='[{"name":"filesystem","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","./data"]}]'
```

启动时 MCPManager 自动连接 server，`list_tools` 发现工具，包装为 `adapters.tools.Tool` 注册进 ToolRegistry。

### 可用 MCP server

| Server | 安装 | 能力 |
|---|---|---|
| filesystem | `npx @modelcontextprotocol/server-filesystem` | 文件读写 |
| github | `npx @modelcontextprotocol/server-github` | GitHub API |
| sqlite | `npx @modelcontextprotocol/server-sqlite` | SQLite 查询 |
| fetch | `npx @modelcontextprotocol/server-fetch` | 网页抓取 |

---

## 4. UI-TARS 桌面 agent

```bash
# 部署 UI-TARS 模型服务（Apache-2.0）
# https://github.com/bytedance/UI-TARS-desktop
export XAGENT_DESKTOP__UI_TARS_URL=http://<ui-tars-host>:<port>
```

---

## 5. OpenHands 编码 agent

```bash
# 部署 OpenHands 运行时（MIT）
# https://github.com/All-Hands-AI/OpenHands
export XAGENT_CODING__OPENHANDS_URL=http://<openhands-host>:<port>
```

---

## 6. Langfuse 可观测

compose 已含 Langfuse v2（自动初始化项目 + key）。直接用：

```bash
# .env（compose 已预设）
XAGENT_OBSERVABILITY__LANGFUSE_HOST=http://localhost:3001
XAGENT_OBSERVABILITY__LANGFUSE_PUBLIC_KEY=pk-lf-xagent-local
XAGENT_OBSERVABILITY__LANGFUSE_SECRET_KEY=sk-lf-xagent-local
```

UI: http://localhost:3001（账号和密码来自 `LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD`）

---

## 7. 检查清单

配置以上任一项后，重启后端即可生效（`xagent serve` 或 `docker compose up -d api`）。
未配置的项自动走降级，不影响其他功能。
