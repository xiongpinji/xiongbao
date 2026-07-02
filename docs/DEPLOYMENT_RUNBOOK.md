# X-Agent 部署 Runbook（单机 / Docker Compose）

> 适用：full 模式单机生产 / 试点部署。lite 模式见根 README。
> 企业 K8s / HA 为后续工作，本文档暂不覆盖。

## 1. 前置

- Docker 24+ / Docker Compose v2
- Python 3.11（仅在需要宿主机调试 API / 跑后端测试时使用）
- Node.js 20+（用于构建 `apps/web/dist`）
- 至少一个当前已接通的 LLM 路径：OpenAI / DeepSeek provider key，或宿主机可访问的 Ollama
- 端口：8000（后端）3000（前端）4000（LiteLLM）6333（Qdrant）5432（Postgres）6379（Redis）3001（Langfuse）

环境与验收约定：

- `XAGENT_DEV_API_TARGET`：前端 dev server 代理到哪个后端，默认 `http://localhost:8000`。
- `E2E_BASE_URL`：Playwright 对哪个前端地址做验收，默认 `http://localhost:3000`。
- `E2E_USERNAME` / `E2E_PASSWORD`：full 模式 Playwright 验收账号；未设置时回退到 `admin/admin`。
- 并行 worktree 开发时，可以把前端 / 后端分别切到独立端口，例如 `E2E_BASE_URL=http://127.0.0.1:4173`、`XAGENT_DEV_API_TARGET=http://127.0.0.1:8100`。
- 后端测试建议从 `apps/api` 目录运行；如果必须从仓库根运行，请先设置 `PYTHONPATH=apps/api`，避免 `ModuleNotFoundError: xagent`。

## 2. private deployment：启动 unified runtime 主链

```bash
cd apps/web
npm install
npm run build

cd ../../deploy/compose
cp .env.example .env
# 编辑 .env：
#   - 生产必填 XAGENT_SECURITY__JWT_SECRET（长随机串）
#   - 若使用 LiteLLM，填写 XAGENT_LLM__PROXY_URL / XAGENT_LLM__PROXY_API_KEY
#   - 若使用宿主机 Ollama，保持默认 host.docker.internal 配置即可
#   - 并行 worktree 验收时，可配合前端 / 后端独立端口：
#       XAGENT_DEV_API_TARGET=http://127.0.0.1:8100
#       E2E_BASE_URL=http://127.0.0.1:4173

docker compose up -d --build
```

这套 compose 会同时启动：`postgres`、`redis`、`qdrant`、`contextforge`、`openfga`、`litellm`、`langfuse`、`api`、`worker`、`web`。

说明：

- `deploy/compose/postgres-init.sh` 会在首次启动 `postgres` 容器时补建 `langfuse`、`contextforge`、`openfga` 这 3 个附加数据库，和 compose 服务保持一致。
- 若之前已经创建过旧 volume，需要执行 `docker compose down -v` 后重新 `up`，或手动在现有 Postgres 中补建这 3 个数据库。
- `api` 负责 `/api/v1/tasks`、`/api/v1/workflows`、`/api/v1/runs/:run_id` 等 unified runtime 主链入口。
- `worker` 负责 full 模式后台长任务；当 Redis / Celery 可用时，后台任务可跨实例续跑。
- compose 默认通过 `host.docker.internal:11434` 访问宿主机 Ollama，并为 `api` / `worker` 配置了 `extra_hosts: ["host.docker.internal:host-gateway"]`，以兼容 Linux Docker。
- compose 中的 `XAGENT_CORS_ORIGINS` 会直接读取 `.env` / `.env.example` 的值；修改 `.env` 后重新启动 compose 即可生效。
- `web` 提供统一 Run Console，容器内直接反代 `api:8000`。
- `apps/web/dist` 不会在镜像内自动构建，因此 `docker compose up` 前必须先执行 `npm run build`。

## 3. 启动后验证

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:3000
```

期望：

- `/health` 返回 `{"status":"ok"}`
- `/ready` 返回 `{"ready":true,...}`
- 前端可打开登录页 / 工作台，并能跳转到 `/runs/:runId`

如果你在并行 worktree 中使用独立端口，请把上面的 `3000/8000` 替换为当前 worktree 的实际前后端端口，并同步设置：

- `XAGENT_DEV_API_TARGET=http://127.0.0.1:<api-port>`
- `E2E_BASE_URL=http://127.0.0.1:<web-port>`
- `E2E_USERNAME=<full-mode-user>`
- `E2E_PASSWORD=<full-mode-password>`

## 4. unified runtime 验证路径

推荐按以下顺序验收主链：

1. 登录后在「对话」页提交一个任务。
2. 页面应跳转到 `Run Console`（`/runs/:runId`）。
3. `Run Console` 中至少能看到：概览、Timeline、Validation / Risk / Replay / Resume 面板。
4. 若走工作流入口，审批型工作流应在 `delivery.resume` 中暴露审批续跑指针。
5. 若走后台任务入口，`delivery.replay` 应指向 `/api/v1/tasks/:task_id`，运行中任务还会暴露 `delivery.resume` 续看指针。

## 5. 宿主机调试模式（可选）

如果不想通过 compose 内的 `api` / `worker` 排障，也可以只启动依赖服务，然后在宿主机运行后端：

```bash
cd deploy/compose
docker compose up -d postgres redis qdrant litellm langfuse

cd ../../apps/api
# PowerShell: $env:PYTHONPATH = (Get-Location).Path
# Bash:       export PYTHONPATH="$PWD"
pip install -e ".[dev]"
XAGENT_MODE=full xagent serve
```

此模式适合本地调试，但不是本文档推荐的 private deployment 交付形态。

## 6. 登录与鉴权

- lite：匿名可用（演示）。默认 admin / admin（内置）。
- full / enterprise：`require_auth` 自动开启。用 `POST /api/v1/auth/login` 换 token，前端在「设置」页填入，或使用 `Authorization: Bearer <token>`。
- 接 Keycloak：设置 `XAGENT_SECURITY__OIDC_JWKS_URL` + `OIDC_ISSUER`，启用 RS256 验签（OIDC 回调端点 `/api/v1/auth/oidc/callback`）。

## 7. 安全检查清单（上线前）

- [ ] `XAGENT_SECURITY__JWT_SECRET` 已改为长随机串
- [ ] Langfuse 的 `NEXTAUTH_SECRET` / `SALT` 已改为生产随机值
- [ ] Langfuse 初始管理员密码（默认 `admin12345`）已修改或禁用初始化默认账号
- [ ] `XAGENT_CORS_ORIGINS` 不含 `*`
- [ ] `require_auth` 未被显式关闭
- [ ] 默认 admin / admin 已改密（`UserStore` 或接 Keycloak）
- [ ] `python scripts/license_check.py` 通过（无 AGPL / GPL / ELv2）
- [ ] 数据库 / Redis / Qdrant 不直接公网暴露（经 Nginx / 网关）
- [ ] HTTPS（Nginx 终止 TLS）

## 8. 可观测

- Langfuse：http://localhost:3001（trace / prompt / evals）
- Prometheus 指标：`/metrics`；Grafana 仪表板导入 `deploy/grafana/xagent-dashboard.json`
- 后端日志：structlog JSON 输出到 stdout
- 健康探针：`/health`（liveness）`/ready`（readiness）

## 8.1 Worker（后台长任务）

full 模式下 compose 含 `worker` 服务，后台任务走 Celery（Redis broker）：

```bash
# compose 已含 worker；单独排障时可手动启动
celery -A xagent.worker.celery_app worker --loglevel=info
```

要点：

- `/api/v1/tasks` 提交任务：full + Celery 可用时走 `worker`，否则降级为进程内后台任务。
- Celery 提交时会先把 `tenant_id / owner_id / kind / input / backend / status` 落到 `agent_tasks`；worker 完成后会继续回写最终 `status / result / error / timestamps`。
- `GET /api/v1/tasks` 列表会优先回查 `agent_tasks` 中的持久化状态，必要时再回退到 Celery backend / 进程内 metadata，避免 Celery 任务长期伪装成 `pending`。
- `/api/v1/runs/:run_id` 会把后台任务统一映射为 Run Console 视图。
- 运行中任务会暴露 `resume` 指针，便于前端或外部入口继续追踪。

## 8.2 Keycloak SSO（企业）

1. 部署 Keycloak，导入 realm：`deploy/keycloak/xagent-realm.json`
2. 配置后端：`XAGENT_SECURITY__OIDC_JWKS_URL=http://<keycloak>/realms/xagent/protocol/openid-connect/certs`
   + `XAGENT_SECURITY__OIDC_ISSUER=xagent-api`
3. token 走 RS256 / JWKS 验签；`realm_access.roles` 映射为 X-Agent 角色。

## 8.3 限流

- 进程内：120 req / min（默认）；Redis 可用时自动切换分布式限流。
- 健康探针 / metrics 豁免。超限返回 429 + `Retry-After`。

## 9. 备份

- Postgres：`pg_dump`
- Qdrant：collection 快照
- 审计链：`GET /api/v1/audit/export`（防篡改哈希链，可离线校验）

## 10. 故障排查

| 现象 | 排查 |
|---|---|
| `web` 容器启动失败 | 先确认 `apps/web/dist` 已执行 `npm run build` 生成 |
| 启动报「生产配置校验失败」 | 检查 `JWT_SECRET` / `CORS` / `require_auth` |
| `/ready` 返回 503 | 查看 `components` 字段定位 DB / 缓存依赖 |
| `Run Console` 打不开运行详情 | 检查 `/api/v1/runs/:run_id` 与 `/api/v1/tasks/:task_id` 是否返回 200 |
| 后台任务一直 pending | 查看 `worker` 日志，确认 Redis broker 与 Celery 已连通 |
| LLM 调用失败 | 查看 LiteLLM Proxy 日志（`:4000`）或宿主机 Ollama |
| 403 越权 | 角色 / 权限不足，调用 `/auth/me` 查看角色 |
