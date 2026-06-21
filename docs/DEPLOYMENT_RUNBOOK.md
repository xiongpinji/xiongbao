# X-Agent 部署 Runbook（单机 / Docker Compose）

> 适用：full 模式单机生产/试点部署。lite 模式见根 README。
> 企业 K8s/HA 为后续工作，本文档暂不覆盖。

## 1. 前置

- Docker 24+ / Docker Compose v2
- 至少一个 LLM provider key（OpenAI / DeepSeek / Anthropic 任一）
- 端口：8000(后端) 3000(前端) 4000(LiteLLM) 6333(Qdrant) 5432(PG) 6379(Redis) 3001(Langfuse)

## 2. 起依赖服务

```bash
cd deploy/compose
cp .env.example .env
# 编辑 .env：必填 XAGENT_LLM__OPENAI_API_KEY（或经 LiteLLM Proxy 配置）
#          生产必填 XAGENT_SECURITY__JWT_SECRET（长随机串）
docker compose up -d
```

服务清单：postgres / redis / qdrant / litellm / langfuse。健康检查内置。

## 3. 后端

```bash
cd apps/api
pip install -e ".[dev]"          # 或构建镜像
# full 模式
XAGENT_MODE=full xagent serve    # 默认 0.0.0.0:8000
```

验证：
```bash
curl localhost:8000/health        # {"status":"ok"}
curl localhost:8000/ready         # {"ready":true,...}
```

## 4. 前端 / 桌面

```bash
cd apps/web
npm install && npm run build      # 产物 dist/
# 开发：npm run dev（:3000，代理 /api -> :8000）
# 桌面：cd ../desktop && cargo tauri dev|build
```

## 5. 登录与鉴权

- lite：匿名可用（演示）。默认 admin/admin（内置）。
- full/enterprise：`require_auth` 自动开启。用 `POST /api/v1/auth/login` 换 token，
  前端在「设置」页填入，或 `Authorization: Bearer <token>`。
- 接 Keycloak：设 `XAGENT_SECURITY__OIDC_JWKS_URL` + `OIDC_ISSUER`，启用 RS256 验签（OIDC 回调端点 `/api/v1/auth/oidc/callback`）。

## 6. 安全检查清单（上线前）

- [ ] `XAGENT_SECURITY__JWT_SECRET` 已改为长随机串
- [ ] `XAGENT_CORS_ORIGINS` 不含 `*`
- [ ] `require_auth` 未被显式关闭
- [ ] 默认 admin/admin 已改密（`UserStore` 或接 Keycloak）
- [ ] `python scripts/license_check.py` 通过（无 AGPL/GPL/ELv2）
- [ ] 数据库/Redis/Qdrant 不直接公网暴露（经 Nginx/网关）
- [ ] HTTPS（Nginx 终止 TLS）

## 7. 可观测

- Langfuse：http://localhost:3001（trace / prompt / evals）
- Prometheus 指标：`/metrics`；Grafana 仪表板导入 `deploy/grafana/xagent-dashboard.json`
- 后端日志：structlog JSON 到 stdout
- 健康探针：`/health`（liveness）`/ready`（readiness）

## 7.1 Celery worker（后台长任务）

full 模式下 compose 含 `worker` 服务，后台任务走 Celery（Redis broker）：

```bash
# compose 已含 worker；单独启动：
celery -A xagent.worker.celery_app worker --loglevel=info
```

- `/api/v1/tasks` 提交任务：full+Celery 可用走 Celery，否则进程内降级。
- 任务结果存 Redis backend，跨实例可查。

## 7.2 Keycloak SSO（企业）

1. 部署 Keycloak，导入 realm：`deploy/keycloak/xagent-realm.json`
2. 配置后端：`XAGENT_SECURITY__OIDC_JWKS_URL=http://<keycloak>/realms/xagent/protocol/openid-connect/certs`
   + `XAGENT_SECURITY__OIDC_ISSUER=xagent-api`
3. token 走 RS256/JWKS 验签；realm_access.roles 映射为 X-Agent 角色。

## 7.3 限流

- 进程内：120 req/min（默认）；Redis 可用时自动切换分布式限流。
- 健康探针 / metrics 豁免。超限 429 + Retry-After。

## 8. 备份

- Postgres：`pg_dump`
- Qdrant：collection 快照
- 审计链：`GET /api/v1/audit/export`（防篡改哈希链，可离线校验）

## 9. 故障排查

| 现象 | 排查 |
|---|---|
| 启动报「生产配置校验失败」 | 检查 JWT_SECRET / CORS / require_auth |
| `/ready` 503 | 查 components 字段定位 DB/缓存 |
| LLM 调用失败 | 查 LiteLLM Proxy 日志 (:4000) 与 key |
| 402 Payment Required | 配额超限，`/billing/summary` 查用量 |
| 403 越权 | 角色/权限不足，`/auth/me` 查角色 |
