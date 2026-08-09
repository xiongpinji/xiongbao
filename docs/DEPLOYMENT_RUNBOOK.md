# X-Agent 部署 Runbook（单机 / Docker Compose）

> 适用：full 模式单机生产 / 试点部署。lite 模式见根 README。
> 企业 K8s / HA 为后续工作，本文档暂不覆盖。
> 发布执行、DB 迁移签字、回滚与 smoke 证据归档请使用 `docs/RELEASE_RUNBOOK_V1.md`。
> dev / staging / prod 配置基线与 secret 注入说明见 `docs/ENVIRONMENT_BASELINE_V1.md`。
> 若需要交付给管理员 / 运维 / 试点负责人的成套材料入口，请先看 `docs/DELIVERY_MATERIALS_INDEX_V1.md`。

## 1. R2 单一路径

R2 本地 full Compose 试运行只使用 `deploy/compose/docker-compose.yml` 与 `deploy/compose/r2.env.local`。根目录 `docker-compose.yml` 只是开发兼容入口，不是 R2 入口；不要用根 Compose 作为 R2 验收依据。

R2 执行顺序：

```powershell
pwsh -File scripts/r2-preflight.ps1 -Init
pwsh -File scripts/r2-preflight.ps1
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local up -d --build postgres redis qdrant api worker web
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local --profile mcp --profile observability up -d platform-mcp prometheus grafana
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local down
```

R2 边界：

- 不运行 `docker compose down -v`，不删除 volume。
- 本阶段不启用 `gateway`、`tracing`、`federation` profile。
- `mcp` 与 `observability` 只在核心六服务验收后按需启用。
- 所有浏览器验收统一使用 `http://127.0.0.1:18080`。
- 上述命令是运行入口说明，不代表 Docker、Compose、Ollama 或任何容器当前已经就绪或已启动。

## 2. 前置

- Docker 24+ / Docker Compose v2
- Python 3.11（仅在需要宿主机调试 API / 跑后端测试时使用）
- Node.js 20+（用于构建 `apps/web/dist`）
- 至少一个当前已接通的 LLM 路径：OpenAI / DeepSeek provider key，或宿主机可访问的 Ollama
- R2 默认端口：18000（后端）18080（前端）15432（Postgres）16379（Redis）16333/16334（Qdrant）18100（Platform MCP）19090（Prometheus）13002（Grafana）

环境与验收约定：

- `XAGENT_DEV_API_TARGET`：前端 dev server 代理到哪个后端，默认 `http://localhost:8000`。
- `E2E_BASE_URL`：Playwright 对哪个前端地址做验收；R2 Compose 基线使用 `http://127.0.0.1:18080`。
- `E2E_USERNAME` / `E2E_PASSWORD`：full 模式 Playwright 验收账号；必须显式设置，不提供默认账号回退。
- 并行 worktree 开发时，可以把前端 / 后端分别切到独立端口，例如 `E2E_BASE_URL=http://127.0.0.1:4173`、`XAGENT_DEV_API_TARGET=http://127.0.0.1:8100`。
- 后端测试建议从 `apps/api` 目录运行；如果必须从仓库根运行，请先设置 `PYTHONPATH=apps/api`，避免 `ModuleNotFoundError: xagent`。

## 3. 旧 private deployment：启动 unified runtime 主链

```bash
cd apps/web
npm install
npm run build

cd ../..
pwsh -File scripts/r2-preflight.ps1 -Init
# 冷启动 rehearsal 前，可把 rehearsal 参数合入 deploy/compose/r2.env.local，
# 但 R2 compose 命令仍必须显式使用 --env-file deploy/compose/r2.env.local。
# 编辑 deploy/compose/r2.env.local：
#   - 生产必填 XAGENT_SECURITY__JWT_SECRET（长随机串）
#   - 生产必填 LANGFUSE_NEXTAUTH_SECRET / LANGFUSE_SALT / LANGFUSE_INIT_USER_PASSWORD
#   - 若使用 LiteLLM，填写 XAGENT_LLM__PROXY_URL / XAGENT_LLM__PROXY_API_KEY
#   - 若使用宿主机 Ollama，保持默认 host.docker.internal 配置即可
#   - R2 Compose 基线前端对外暴露在 18080，请把 XAGENT_CORS_ORIGINS 对齐到实际浏览器来源，示例：
#       XAGENT_CORS_ORIGINS=["http://127.0.0.1:18080"]
#   - 并行 worktree 验收时，可配合前端 / 后端独立端口：
#       XAGENT_DEV_API_TARGET=http://127.0.0.1:8100
#       E2E_BASE_URL=http://127.0.0.1:4173

docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local up -d --build postgres redis qdrant api worker web
```

R2 核心路径只启动：`postgres`、`redis`、`qdrant`、`api`、`worker`、`web`。`platform-mcp`、`prometheus`、`grafana` 是后续可选服务；本阶段不启用 `gateway`、`tracing`、`federation`。

说明：

- `deploy/compose/postgres-init.sh` 会在首次启动 `postgres` 容器时补建 `langfuse`、`contextforge`、`openfga` 这 3 个附加数据库，和 compose 服务保持一致。
- 若之前已经创建过旧 volume，不要执行 `docker compose down -v`；先备份并确认处置方案，R2 本阶段只允许使用不带 `-v` 的 `down`。
- `api` 负责 `/api/v1/tasks`、`/api/v1/workflows`、`/api/v1/runs/:run_id` 等 unified runtime 主链入口。
- `worker` 负责 full 模式后台长任务；当 Redis / Celery 可用时，后台任务可跨实例续跑。
- compose 默认通过 `host.docker.internal:11434` 访问宿主机 Ollama，并为 `api` / `worker` 配置了 `extra_hosts: ["host.docker.internal:host-gateway"]`，以兼容 Linux Docker。
- `deploy/compose/.env.example` 与 `.env.rehearsal` 已包含冷启动加固相关参数：`XAGENT_LLM__REQUEST_TIMEOUT_SECONDS=150`、`XAGENT_LLM__WARMUP_ENABLED=true`、`XAGENT_LLM__WARMUP_PROMPT=回复一个字：好`、`XAGENT_LLM__WARMUP_MAX_TOKENS=8`、`XAGENT_LLM__WARMUP_WAIT_TIMEOUT_SECONDS=30`、`XAGENT_LLM__WARMUP_POLL_INTERVAL_SECONDS=1`。复制到 `.env` 后应保留这组基线。
- compose 中的 `XAGENT_CORS_ORIGINS` 会直接读取 `deploy/compose/r2.env.local` 的值；R2 Compose 基线前端对外端口是 `18080`，因此浏览器来源应写成 `http://127.0.0.1:18080`。
- `web` 提供统一 Run Console，容器内直接反代 `api:8000`，R2 对外浏览器入口是 `http://127.0.0.1:18080`。
- `apps/web/dist` 不会在镜像内自动构建，因此 `docker compose up` 前必须先执行 `npm run build`。

## 3.1 Ollama 冷启动加固

当前基线默认把本地模型冷启动视为常态，而不是异常：

- `XAGENT_LLM__REQUEST_TIMEOUT_SECONDS=150`：给首次拉起大模型留足时间。`qwen2.5vl:7b` 这类模型在宿主机冷启动时，可能同时发生模型装载、显存分配、KV cache 初始化；若仍使用较短默认超时，首个真实请求很容易在模型可用前就超时。
- `XAGENT_LLM__WARMUP_ENABLED=true`：在服务正式接流量前，先用最小 prompt 触发一次模型装载。
- `XAGENT_LLM__WARMUP_PROMPT=回复一个字：好` + `XAGENT_LLM__WARMUP_MAX_TOKENS=8`：把 warmup 成本压到最低，只验证链路可达与模型可响应。
- `XAGENT_LLM__WARMUP_WAIT_TIMEOUT_SECONDS=120` + `XAGENT_LLM__WARMUP_POLL_INTERVAL_SECONDS=1`：对 `qwen2.5vl:7b` 这类冷启动明显慢于 30 秒的本地模型，给启动阶段更现实的 120 秒窗口，让 warmup 更有机会在首个真实请求前完成，而不是过早失败后把冷启动成本转嫁给用户请求。

为什么 `api` 和 `worker` 都要 warm up：

- `api` 可能是栈重启后的第一个调用方：登录后的即时试跑、健康后第一条 `/api/v1/agents/run` 都会命中它。
- `worker` 也可能是第一个真实 LLM 调用方：`/api/v1/tasks`、工作流后台步骤、异步任务续跑都可能绕过交互式前台，直接由 Celery worker 首次触发模型。
- 因此只预热 `api` 不足以覆盖 full 模式主链；`api`、`worker` 各自启动前都执行一次 warmup，才能把冷启动抖动压到最小。

## 3.2 启动顺序与 warmup 日志

当前 Compose 命令链路如下：

- `api`：`python -m alembic upgrade head` -> `python -m xagent.cli warmup` -> `uvicorn xagent.main:app`
- `worker`：`python -m xagent.cli warmup` -> `celery -A xagent.worker.celery_app worker --loglevel=info`

warmup 实际行为：

- 若配置了 `XAGENT_LLM__PROXY_URL`，warmup 走 LiteLLM Proxy。
- 否则若配置了 `XAGENT_LLM__OLLAMA_BASE_URL`，warmup 直接请求宿主机 Ollama 的 `/api/tags` 与 `/api/chat`。
- 若关闭了 `XAGENT_LLM__WARMUP_ENABLED`，或既没配 proxy 也没配 Ollama base URL，则 warmup 会跳过。

日志判读：

- 成功：日志名为 `ollama_warmup_succeeded`，会带上 `model`、`route`、`elapsed_seconds`。
- 失败：日志名为 `ollama_warmup_failed`，会带上 `error`、`model`、`route`、`wait_timeout_seconds`。
- 当前 Compose 命令使用 `(python -m xagent.cli warmup || true)`，所以 warmup 失败不会阻止 `api` / `worker` 继续拉起；这意味着“容器已启动”不等于“冷启动已验证通过”，必须结合日志与首个真实请求一起确认。

## 4. 启动后验证

```bash
curl http://127.0.0.1:18000/health
curl http://127.0.0.1:18000/ready
curl http://127.0.0.1:18080
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

## 4.1 显式冷启动验证流程（Ollama rehearsal）

在演练或上线前，建议至少跑一次“从冷模型到首个真实 agent 请求”的完整验证。以下步骤以 `.env.rehearsal` 中的 `qwen2.5vl:7b` 为例：

1. 确认宿主机 Ollama 已拉到目标模型：`ollama pull qwen2.5vl:7b`
2. 在宿主机显式卸载模型，制造冷启动条件：

```bash
ollama stop qwen2.5vl:7b
```

3. 将 rehearsal 参数合入 `deploy/compose/r2.env.local`，确保本次 cold-start rehearsal 实际使用 `qwen2.5vl:7b` 和 warmup 参数，然后重启 R2 核心 Compose：

```bash
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local down
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local up -d --build postgres redis qdrant api worker web
```

4. 观察 warmup 日志，确认 `api` 和 `worker` 都至少产出一次成功或失败信号：

```bash
docker compose logs api worker --since=10m | grep -E "ollama_warmup_(succeeded|failed)"
```

判读要求：

- 理想情况：`api`、`worker` 都出现 `ollama_warmup_succeeded`。
- 若任一服务出现 `ollama_warmup_failed`，先检查宿主机 Ollama 是否存活、模型名是否与 `.env` 一致、`host.docker.internal:11434` 是否可达，再继续下面的首个真实请求验证。

5. 做基础健康检查：

```bash
curl http://127.0.0.1:18000/health
curl http://127.0.0.1:18000/ready
curl http://127.0.0.1:18080
```

6. 做鉴权引导。full 模式不会内置 `admin/admin`；演练环境可以先自助注册一个用户，已有用户则直接登录：

```bash
curl -X POST http://127.0.0.1:18000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"rehearsal-admin","password":"ChangeMe-123456","tenant_id":"rehearsal"}'
```

从返回 JSON 里取出 `access_token`，若用户已存在则改用：

```bash
curl -X POST http://127.0.0.1:18000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"rehearsal-admin","password":"ChangeMe-123456","tenant_id":"rehearsal"}'
```

7. 用拿到的 token 发送首个真实 agent 请求，验证冷启动后主链是否可用：

```bash
TOKEN=<上一步返回的 access_token>

curl -X POST http://127.0.0.1:18000/api/v1/agents/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"goal":"请用一句话确认 Ollama 冷启动验证通过"}'
```

期望：

- 返回 200，且响应里包含 `run_id` / `final_answer` / `steps` 等结果字段。
- 若这一步是重启后的首个真实 LLM 请求，整体耗时仍可能明显高于热机请求；但在 150 秒超时基线内应能完成，而不是过早超时。
- 成功后可在浏览器打开 `http://127.0.0.1:18080`，登录同一账号，确认 Run Console 能查看对应运行记录。

## 5. unified runtime 验证路径

推荐按以下顺序验收主链：

1. 登录后在「对话」页提交一个任务。
2. 页面应跳转到 `Run Console`（`/runs/:runId`）。
3. `Run Console` 中至少能看到：概览、Timeline、Validation / Risk / Replay / Resume 面板。
4. 若走工作流入口，审批型工作流应在 `delivery.resume` 中暴露审批续跑指针。
5. 若走后台任务入口，`delivery.replay` 应指向 `/api/v1/tasks/:task_id`，运行中任务还会暴露 `delivery.resume` 续看指针。

## 6. 宿主机调试模式（可选）

如果不想通过 compose 内的 `api` / `worker` 排障，也可以只启动依赖服务，然后在宿主机运行后端：

```bash
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local up -d postgres redis qdrant

cd apps/api
# PowerShell: $env:PYTHONPATH = (Get-Location).Path
# Bash:       export PYTHONPATH="$PWD"
pip install -e ".[dev]"
XAGENT_MODE=full xagent serve
```

此模式适合本地调试，但不是本文档推荐的 private deployment 交付形态。本阶段宿主机调试也只能启动核心依赖 `postgres`、`redis`、`qdrant`，不得启动 `litellm`、`langfuse` 或 `gateway` / `tracing` / `federation` profile。

## 7. 登录与鉴权

- lite：匿名可用（演示）。默认 admin / admin（内置）。
- full / enterprise：`require_auth` 自动开启，且不会内置默认 `admin/admin`。当前基线可通过 `POST /api/v1/auth/register` 自助引导首个演练账号，或使用已接入的 Keycloak / DB 用户源，再通过 `POST /api/v1/auth/login` 换 token；前端在「设置」页填入，或使用 `Authorization: Bearer <token>`。
- 接 Keycloak：设置 `XAGENT_SECURITY__OIDC_JWKS_URL` + `OIDC_ISSUER`，启用 RS256 验签（OIDC 回调端点 `/api/v1/auth/oidc/callback`）。

## 8. 安全检查清单（上线前）

- [ ] `XAGENT_SECURITY__JWT_SECRET` 已改为长随机串
- [ ] Langfuse 的 `NEXTAUTH_SECRET` / `SALT` 已改为生产随机值
- [ ] Langfuse 初始管理员密码已通过 `LANGFUSE_INIT_USER_PASSWORD` 显式设置为强密码
- [ ] `XAGENT_CORS_ORIGINS` 已对齐当前前端实际来源（R2 Compose 基线为 `http://127.0.0.1:18080`），且不含 `*`
- [ ] `require_auth` 未被显式关闭
- [ ] full / enterprise 管理员来自显式用户源（Keycloak / DB / 初始化流程），不存在默认 admin / admin
- [ ] `python scripts/license_check.py` 通过（无 AGPL / GPL / ELv2）
- [ ] 数据库 / Redis / Qdrant 不直接公网暴露（经 Nginx / 网关）
- [ ] HTTPS（Nginx 终止 TLS）

## 9. 可观测

- Langfuse：http://localhost:3001（trace / prompt / evals）
- Prometheus 指标：`/metrics`；Grafana 仪表板导入 `deploy/grafana/xagent-dashboard.json`
- 后端日志：structlog JSON 输出到 stdout
- 健康探针：`/health`（liveness）`/ready`（readiness）
- Ollama 预热日志：`ollama_warmup_succeeded` / `ollama_warmup_failed`

## 9.1 Worker（后台长任务）

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

## 9.2 Keycloak SSO（企业）

1. 部署 Keycloak，导入 realm：`deploy/keycloak/xagent-realm.json`
2. 配置后端：`XAGENT_SECURITY__OIDC_JWKS_URL=http://<keycloak>/realms/xagent/protocol/openid-connect/certs`
   + `XAGENT_SECURITY__OIDC_ISSUER=xagent-api`
3. token 走 RS256 / JWKS 验签；`realm_access.roles` 映射为 X-Agent 角色。

## 9.3 限流

- 进程内：120 req / min（默认）；Redis 可用时自动切换分布式限流。
- 健康探针 / metrics 豁免。超限返回 429 + `Retry-After`。

## 10. 备份

- Postgres：`pg_dump`
- Qdrant：collection 快照
- 审计链：`GET /api/v1/audit/export`（防篡改哈希链，可离线校验）

## 11. 故障排查

| 现象 | 排查 |
|---|---|
| `web` 容器启动失败 | 先确认 `apps/web/dist` 已执行 `npm run build` 生成 |
| 启动报「生产配置校验失败」 | 检查 `JWT_SECRET` / `CORS` / `require_auth` |
| `/ready` 返回 503 | 查看 `components` 字段定位 DB / 缓存依赖 |
| `Run Console` 打不开运行详情 | 检查 `/api/v1/runs/:run_id` 与 `/api/v1/tasks/:task_id` 是否返回 200 |
| 后台任务一直 pending | 查看 `worker` 日志，确认 Redis broker 与 Celery 已连通 |
| 看到 `ollama_warmup_failed` | 检查宿主机 Ollama 进程、模型名、`host.docker.internal:11434` 连通性，并重跑 3.1 的冷启动验证 |
| LLM 调用失败 | 查看 LiteLLM Proxy 日志（`:4000`）或宿主机 Ollama |
| 403 越权 | 角色 / 权限不足，调用 `/auth/me` 查看角色 |
