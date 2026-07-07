# X-Agent Environment Baseline v1

> 用途：说明 dev / staging / prod 的配置基线、secret 来源与危险默认值禁用策略。
>
> 本文档是发布准备证据，不代表目标环境已完成演练。目标环境部署与演练证据仍由 R4 补齐。

---

## 1. 环境分层

| 环境 | 推荐模式 | 主要用途 | 是否可用默认账号 | 是否可用弱 secret |
|---|---|---|---|---|
| dev / local | `lite` | 本地开发、页面调试、离线 smoke | 仅 lite 可用 `admin/admin` | 仅 lite 内置 dev JWT |
| staging | `full` | PR 合并前演练、客户试点前验收 | 不可用默认账号 | 不可用 |
| prod | `full` 或后续 `enterprise` | 正式受控私有部署 | 不可用默认账号 | 不可用 |

规则：

- `lite` 只用于本地开发 / demo / 快速排障，不作为正式发布环境。
- `full` 启用 Postgres、Redis、Qdrant、Langfuse / LiteLLM 等外部依赖，并要求显式 secret。
- `enterprise` 当前是 K8s / HA 方向的接入点，仍需后续平台化验证。

---

## 2. 配置基线

| 配置域 | dev / lite | staging / full | prod / full |
|---|---|---|---|
| `XAGENT_MODE` | `lite` | `full` | `full` 或经审批的 `enterprise` |
| DB | 默认 SQLite | Postgres，独立数据库 | 托管或受控 Postgres，备份策略已启用 |
| Cache | 进程内缓存可接受 | Redis 必须可用 | Redis 受控部署，不公网裸露 |
| Vector store | Qdrant memory / local | Qdrant 服务 | Qdrant 受控部署，需快照策略 |
| LLM | Ollama / mock / provider key | 至少一条真实 LLM 路径 | 明确 provider、额度、限流和故障联系人 |
| Auth | lite 可匿名 / 内置 admin | 必须显式用户源 | Keycloak / DB / 企业 IdP，默认账号禁用 |
| CORS | 可指向本机端口 | 只允许 staging 域名 | 只允许生产域名，不允许 `*` |
| Observability | 可关闭 | Langfuse / metrics 建议开启 | Langfuse / metrics / 日志采集必须有责任人 |
| Media providers | 可用 null provider | 如纳入试点需配置真实 provider | 如纳入交付需配置真实 provider 和额度 |

---

## 3. Secret 清单

| 名称 | 用途 | dev / lite | staging / prod 来源 | 注入方式 |
|---|---|---|---|---|
| `XAGENT_SECURITY__JWT_SECRET` | HS256 JWT 签名 | lite 内置 dev secret | Secret manager / `.env` / CI secret / K8s secret | compose env；Helm `security.jwtSecret` |
| `XAGENT_SECURITY__OIDC_JWKS_URL` | OIDC JWKS 验签 | 可留空 | IdP / Keycloak 配置 | env / Helm values |
| `XAGENT_SECURITY__OIDC_ISSUER` | OIDC issuer 校验 | 可留空 | IdP / Keycloak 配置 | env / Helm values |
| `XAGENT_LLM__PROXY_API_KEY` | LiteLLM proxy 访问 | 可留空 | Secret manager / `.env` / CI secret | env |
| `XAGENT_LLM__OPENAI_API_KEY` | OpenAI 直连 | 可留空 | Secret manager / provider vault | env / LiteLLM config |
| `XAGENT_LLM__DEEPSEEK_API_KEY` | DeepSeek 直连 | 可留空 | Secret manager / provider vault | env / LiteLLM config |
| `XAGENT_OBSERVABILITY__LANGFUSE_PUBLIC_KEY` | Langfuse public key | 可留空 | Langfuse project | env |
| `XAGENT_OBSERVABILITY__LANGFUSE_SECRET_KEY` | Langfuse secret key | 可留空 | Secret manager / Langfuse project | env |
| `LANGFUSE_NEXTAUTH_SECRET` | Langfuse auth secret | 不需要 | Secret manager / `.env` / CI secret | compose env |
| `LANGFUSE_SALT` | Langfuse salt | 不需要 | Secret manager / `.env` / CI secret | compose env |
| `LANGFUSE_INIT_USER_PASSWORD` | Langfuse 初始化用户密码 | 不需要 | Secret manager / one-time bootstrap | compose env |
| `POSTGRES_PASSWORD` | Postgres 服务密码 | compose 示例可本地使用 | Secret manager / DB 平台 | compose env / 托管 DB |
| `XAGENT_MEDIA__OPENAI_IMAGE_API_KEY` | 图像 provider | 可留空 | Secret manager / provider vault | env |
| `XAGENT_MEDIA__KLING_API_KEY` | 可灵 provider | 可留空 | Secret manager / provider vault | env |
| `XAGENT_MEDIA__JIMENG_API_KEY` | 即梦 provider | 可留空 | Secret manager / provider vault | env |
| `XAGENT_MEDIA__GENERIC_VIDEO_API_KEY` | 通用视频 provider | 可留空 | Secret manager / provider vault | env |

约束：

- staging / prod secret 不得写入 Git。
- `.env.example` 只作为变量清单，不作为 staging / prod 可直接复用文件。
- 通过命令行传入 Helm value 会进入 shell history 的环境，正式部署应由 CI secret store 或平台 secret 管理注入。

---

## 4. 注入方式

### 4.1 Docker Compose

1. 从模板复制：

```powershell
cd deploy\compose
Copy-Item .env.example .env
```

2. 在 `.env` 中填入真实值：

```text
XAGENT_SECURITY__JWT_SECRET=<32+ chars random>
LANGFUSE_NEXTAUTH_SECRET=<random>
LANGFUSE_SALT=<random>
LANGFUSE_INIT_USER_PASSWORD=<strong password>
POSTGRES_PASSWORD=<strong password>
XAGENT_CORS_ORIGINS=["https://staging.example.com"]
```

3. 校验：

```powershell
docker compose --env-file .env config --quiet
```

缺少 `XAGENT_SECURITY__JWT_SECRET`、`LANGFUSE_NEXTAUTH_SECRET`、`LANGFUSE_SALT` 或 `LANGFUSE_INIT_USER_PASSWORD` 时，compose 必须失败。

### 4.2 Helm

当前 Helm v1 对 `security.jwtSecret` 使用 `required` fail-fast。最小渲染：

```powershell
helm template xagent deploy/helm --set api.enabled=true --set security.jwtSecret=<32+ chars random>
```

生产建议：

- 由 CI secret store 或平台 secret manager 注入 `security.jwtSecret`。
- DB / Redis / Qdrant URL 使用托管服务或平台内 Secret / ConfigMap 管理。
- 如目标平台要求 secretRef 而非 value 注入，应在后续平台化任务中扩展 Helm chart；当前 v1 文档不把 secretRef 能力伪装为已完成。

---

## 5. 危险默认值禁用策略

### 5.1 应用层

`Settings.validate_for_production()` 在 `full` / `enterprise` 模式下拒绝：

- `XAGENT_CORS_ORIGINS` 包含 `*`。
- `XAGENT_SECURITY__JWT_SECRET` 为空、旧占位值或长度少于 32 字符。
- `XAGENT_SECURITY__REQUIRE_AUTH=false`。

`get_user_store()` 仅在 `lite` 模式 seed `admin/admin`。`full` / `enterprise` 不再内置默认管理员。

### 5.2 Compose

compose 对以下值使用 shell required 语义，缺失或空值时拒绝渲染 / 启动：

- `XAGENT_SECURITY__JWT_SECRET`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_SALT`
- `LANGFUSE_INIT_USER_PASSWORD`

`POSTGRES_PASSWORD=xagent` 仍保留为本地 compose 示例值；staging / prod 必须覆盖为强密码或使用托管数据库凭据。

### 5.3 Helm

Helm chart 对 `security.jwtSecret` fail-fast。缺失时 `helm template` 失败；提供强 secret 后 API / worker 模板均注入 `XAGENT_SECURITY__JWT_SECRET`。

---

## 6. 发布前环境验收

发布或演练前至少记录：

```powershell
# app config
python -c "from xagent.infra.settings import get_settings; print(get_settings().validate_for_production())"

# compose
docker compose --env-file .env config --quiet

# helm
helm template xagent deploy/helm --set api.enabled=true --set security.jwtSecret=<32+ chars random>
```

运行中环境至少记录：

```powershell
curl.exe -f http://<api-host>/health
curl.exe -f http://<api-host>/ready
curl.exe -f http://<web-host>/
```

登录验收必须使用当前环境显式初始化的账号。full / prod 不接受 `admin/admin` 作为证据。

---

## 7. 剩余缺口

- 目标环境的真实 secret manager / K8s secretRef 接入仍需在 R4 或平台化任务中演练。
- 远端 CI 全绿由 R1 继续闭环。
- 关键页面截图 / 验收记录由 R9 补齐。
- 本文档不证明 staging / prod 已部署，只证明环境基线和 secret 策略已经文档化。
