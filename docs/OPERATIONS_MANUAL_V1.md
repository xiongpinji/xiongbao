# X-Agent 运维手册 v1

> 适用对象：运维值守、发布负责人、试点环境维护人。
>
> 适用范围：当前 `xagent` 单机 / Docker Compose `full` 模式。
>
> 边界：本文档描述“如何值守与处置”，不替代正式发布签字，不把 lite/dev 本地证据冒充为目标环境证据。

---

## 1. 运维目标

当前运维目标是：

- 保证 `api` / `worker` / `web` / 基础依赖可启动、可访问；
- 能快速区分配置问题、依赖问题、登录问题、LLM 路径问题；
- 在试点或受控交付范围内，提供最小可执行的巡检、排障、备份和恢复入口。

当前不承诺：

- 多实例 HA；
- 自动故障转移；
- 完整 SLO / 告警体系已落地；
- 完整容量压测基线已冻结。

---

## 2. 核心服务清单

当前 Compose `full` 模式核心服务：

- `postgres`
- `redis`
- `qdrant`
- `contextforge`
- `openfga`
- `litellm`
- `langfuse`
- `api`
- `worker`
- `web`

主链服务说明：

- `api`：提供健康检查、登录、运行、任务、工作流、Run Console 读模型聚合；
- `worker`：处理后台长任务与工作流执行；
- `web`：工作台入口；
- `postgres` / `redis` / `qdrant`：基础状态与存储依赖；
- `litellm` / `langfuse`：LLM 网关与追踪配套。

---

## 3. 日常巡检清单

每次巡检建议按顺序执行：

### 3.1 服务状态

```powershell
cd deploy\compose
docker compose ps
```

检查：

- `api` / `worker` / `web` 是否 running；
- `postgres` / `redis` / `qdrant` 是否 healthy 或可访问；
- 是否有容器异常重启。

### 3.2 健康探针

```powershell
curl.exe -f http://localhost:8000/health
curl.exe -f http://localhost:8000/ready
curl.exe -f http://localhost:3000
```

检查：

- `/health` 是否 200；
- `/ready` 是否 `ready=true`；
- 前端入口是否 200。

### 3.3 日志抽样

```powershell
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=200 web
```

重点关注：

- JWT secret / CORS 校验失败；
- Alembic migration 失败；
- Redis / Qdrant / Postgres 连通性失败；
- `ollama_warmup_failed`；
- LLM provider 401 / 403 / timeout；
- worker 长时间 pending。

---

## 4. 常见告警信号与第一判断

### 4.1 `/health` 正常但 `/ready` 异常

优先判断依赖连通性：

- Postgres
- Redis
- Qdrant
- 其他 readiness components

做法：

1. 看 `/ready` 返回体；
2. 再看 `api` 日志；
3. 再看对应依赖容器状态。

### 4.2 前端能打开但登录失败

优先排查：

- 当前 full-mode 账号是否真实存在；
- JWT secret 是否正确；
- OIDC / Keycloak 是否配置正确；
- `/api/v1/auth/login` 返回什么。

### 4.3 worker 任务长期 pending

优先排查：

- Redis broker；
- worker 容器是否 running；
- worker 日志是否报错；
- `agent_tasks` 是否已持久化状态。

### 4.4 首次运行特别慢或超时

优先排查：

- 当前是否在走 Ollama 冷启动；
- warmup 是否成功；
- `XAGENT_LLM__REQUEST_TIMEOUT_SECONDS` 是否仍为 150；
- 模型名、provider key、proxy 路径是否一致。

---

## 5. 最小排障路径

### 5.1 配置类问题

常见表现：

- compose config 失败；
- api 启动即退出；
- CORS / JWT / Langfuse secret 校验失败。

优先命令：

```powershell
docker compose --env-file .env config --quiet
docker compose logs --tail=200 api
```

### 5.2 数据库迁移类问题

常见表现：

- api 启动卡在 Alembic；
- `/ready` 不通过；
- 新环境缺表。

优先命令：

```powershell
docker compose run --rm api python -m alembic current
docker compose run --rm api python -m alembic upgrade head
```

说明：历史本地漂移库不能拿来当发布证据，具体边界见 [COMMERCIAL_RELEASE_CHECKLIST_V1.md](COMMERCIAL_RELEASE_CHECKLIST_V1.md)。

### 5.3 LLM 类问题

常见表现：

- 调用超时；
- provider 鉴权失败；
- warmup 失败；
- 首个请求极慢。

优先日志关键字：

- `ollama_warmup_succeeded`
- `ollama_warmup_failed`
- provider 401/403/timeout

### 5.4 前端空白页或 Run Console 无内容

优先排查：

- `apps/web/dist` 是否基于当前候选构建；
- `web` 容器日志；
- `/api/v1/runs/:run_id` 是否返回数据；
- 当前运行是否只在 lite/dev 下被验证过。

---

## 6. 备份与恢复入口

### 6.1 备份

当前最少应备份 Postgres：

```powershell
cd deploy\compose
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
docker compose exec -T postgres pg_dump -U xagent xagent > "backups\xagent-$stamp.sql"
```

若使用 Qdrant 持久化数据，也应记录 snapshot 路径。

### 6.2 恢复

恢复逻辑以 [RELEASE_RUNBOOK_V1.md](RELEASE_RUNBOOK_V1.md) 为准，运维值守至少要知道：

- 先停写入服务；
- 再恢复 Postgres；
- 再切回上一候选；
- 再重做 smoke；
- 最后归档恢复时间与影响范围。

---

## 7. 当前已知运维边界

当前必须明确：

- Grafana / 完整告警体系未在仓库内闭环为正式交付 gate；
- SLO / RTO / RPO 尚未形成正式签字版；
- 负载测试与容量建议尚未闭环为正式发布证据；
- 当前更适合试点 / 受控交付值守，不应口头承诺成熟 SaaS 级运维体系。

---

## 8. 升级与回滚入口

运维值守做升级/回滚时，不应临场自由发挥，统一以：

- [RELEASE_RUNBOOK_V1.md](RELEASE_RUNBOOK_V1.md)
- [ENVIRONMENT_BASELINE_V1.md](ENVIRONMENT_BASELINE_V1.md)

为准。

如果要快速判断当前是否可以升级，先看：

1. 当前候选是否冻结；
2. 当前候选远端 CI 是否覆盖；
3. 当前环境是否具备 R4 演练级输入；
4. 当前是否已有回滚负责人。

---

## 9. 当前结论

这份运维手册可以支撑当前候选的：

- 最小巡检；
- 故障一线分流；
- 发布前后日志查看；
- 备份 / 恢复入口理解。

但它**不代表**：

- 目标环境演练已经完成；
- 可观测体系已经完全商用收口；
- 正式交付 gate 已经全部关闭。
