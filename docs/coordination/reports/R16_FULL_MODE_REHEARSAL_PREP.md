# R16 Full-Mode Rehearsal Prerequisite Checklist

> 日期：2026-07-06
> Owner：Codex
> 范围：R4 full-mode / compose rehearsal 前置条件补齐，不执行目标环境演练

## 1. 结论

R16 已将 R4 当前阻塞拆成可恢复的前置清单和复跑步骤。该清单用于帮助 R4 恢复执行，不构成目标环境或 staging 等价演练完成证据。

当前最小结论：

- `docker compose --env-file .env.example config --quiet` 在缺少 Langfuse 必填 secret 时按预期失败。
- 补齐 R16 演练占位 secret 后，`docker compose --env-file .env.example config --quiet` 可通过。
- 5432 / 6379 / 6333 / 6334 / 3001 / 4000 / 8080 / 8081 当前未监听，说明本机没有可直接复用的 full-stack 运行面。
- R4 恢复前仍必须准备真实或等价 rehearsal secret、full-mode 显式账号、至少一条可用 LLM 路径，并实际启动 compose/full-mode 栈。

## 2. R4 已知阻塞

来自 `delivery-report.md` 的 R4 记录：

- 当前 live stack 是 lite/dev 级别，不能替代 full/staging 发布演练。
- `deploy/compose/.env` / `.env.rehearsal` 缺少 `LANGFUSE_NEXTAUTH_SECRET`、`LANGFUSE_SALT`、`LANGFUSE_INIT_USER_PASSWORD` 一类必填值。
- compose 依赖端口 5432 / 6379 / 6333 / 6334 / 3001 / 4000 / 8080 / 8081 未监听。
- full-mode 不能使用 lite 默认 `admin/admin`，必须准备显式账号来源。
- 还没有形成 full-mode 可用 LLM 路径演练证据。

## 3. Rehearsal 输入清单

### 3.1 候选与构建

- 固定候选 commit / branch / worktree。
- `apps/web/dist` 已由当前候选执行 `npm run build` 生成。
- 当前候选对应的验证证据已可追溯：R1 / R2 / R3 / R13 / R14 等只作为输入证据，不替代 R4 演练。

### 3.2 Compose env

建议从模板生成 rehearsal 专用 env，不把 secret 写入 Git：

```powershell
cd deploy\compose
Copy-Item .env.example .env.rehearsal
```

`.env.rehearsal` 至少补齐：

```text
XAGENT_MODE=full
XAGENT_CORS_ORIGINS=["http://localhost:3000"]
XAGENT_SECURITY__JWT_SECRET=<32+ chars random>
XAGENT_SECURITY__REQUIRE_AUTH=true
LANGFUSE_NEXTAUTH_SECRET=<random>
LANGFUSE_SALT=<random>
LANGFUSE_INIT_USER_PASSWORD=<strong password>
POSTGRES_PASSWORD=<strong password or accepted local rehearsal password>
```

LLM 路径三选一：

```text
# A. 宿主机 Ollama
XAGENT_LLM__OLLAMA_BASE_URL=http://host.docker.internal:11434
XAGENT_LLM__OLLAMA_MODEL=qwen3:4b
XAGENT_LLM__DEFAULT_MODEL=qwen3:4b

# B. LiteLLM Proxy
XAGENT_LLM__PROXY_URL=http://litellm:4000
XAGENT_LLM__PROXY_API_KEY=<proxy key>

# C. 直连 provider
XAGENT_LLM__OPENAI_API_KEY=<provider key>
# or
XAGENT_LLM__DEEPSEEK_API_KEY=<provider key>
```

### 3.3 账号

full / enterprise 不再内置默认 `admin/admin`。R4 开始前必须明确其中一种：

- Keycloak / OIDC 用户源已配置，且有可用于验收的账号。
- DB / 显式初始化流程已创建管理员或验收用户。
- Playwright 使用 `E2E_USERNAME` / `E2E_PASSWORD` 指向该 full-mode 用户。

不得把 lite/dev 的 `admin/admin` 登录结果作为 full-mode rehearsal 证据。

### 3.4 端口与依赖

启动前检查这些端口没有冲突，或由 R4 明确改 compose 端口映射：

| 服务 | 端口 |
|---|---|
| Postgres | 5432 |
| Redis | 6379 |
| Qdrant HTTP / gRPC | 6333 / 6334 |
| Langfuse | 3001 |
| LiteLLM | 4000 |
| ContextForge | 8080 |
| OpenFGA | 8081 |
| API / Web | 8000 / 3000 |

检查命令：

```powershell
Get-NetTCPConnection -LocalPort 5432,6379,6333,6334,3001,4000,8080,8081,8000,3000 -ErrorAction SilentlyContinue
```

## 4. R4 恢复步骤建议

R4 可按以下顺序恢复，不需要重新设计流程：

1. 复制并填写 `deploy/compose/.env.rehearsal`。
2. 执行 `docker compose --env-file .env.rehearsal config --quiet`，必须退出码 0。
3. 在 `apps/web` 执行 `npm ci` 与 `npm run build`，确保 `dist` 属于当前候选。
4. 启动依赖：

```powershell
cd deploy\compose
docker compose --env-file .env.rehearsal up -d --build postgres redis qdrant litellm langfuse contextforge openfga
docker compose --env-file .env.rehearsal ps
```

5. 启动应用：

```powershell
docker compose --env-file .env.rehearsal up -d --build api worker web
docker compose --env-file .env.rehearsal ps
```

6. 记录迁移和启动日志：

```powershell
docker compose --env-file .env.rehearsal logs --tail=200 api > rehearsal-api.log
docker compose --env-file .env.rehearsal logs --tail=200 worker > rehearsal-worker.log
docker compose --env-file .env.rehearsal logs --tail=200 web > rehearsal-web.log
```

7. 执行 smoke：

```powershell
curl.exe -f http://localhost:8000/health
curl.exe -f http://localhost:8000/ready
curl.exe -f http://localhost:3000
```

8. 使用 full-mode 显式账号做登录 / Run Console 验收：

```powershell
cd tests\e2e
$env:E2E_BASE_URL = "http://localhost:3000"
$env:E2E_USERNAME = "<full-mode-user>"
$env:E2E_PASSWORD = "<full-mode-password>"
npx playwright test specs/creative-smoke.spec.ts --project=chromium
```

如 R4 选择完整 full-flow，应继续执行：

```powershell
npx playwright test specs/full-flow.spec.ts --project=chromium
```

## 5. 常见阻塞与恢复

| 阻塞 | 恢复动作 |
|---|---|
| `LANGFUSE_NEXTAUTH_SECRET is missing` | 在 `.env.rehearsal` 填入 `LANGFUSE_NEXTAUTH_SECRET`、`LANGFUSE_SALT`、`LANGFUSE_INIT_USER_PASSWORD` |
| `XAGENT_SECURITY__JWT_SECRET is missing` | 填入 32+ 字符随机 secret；不得恢复弱默认 |
| 端口已被占用 | 停止占用进程，或由 R4 显式记录端口改动；不要静默复用错误服务 |
| `/ready` 失败 | 查看 readiness components 和 `api` 日志，定位 Postgres / Redis / Qdrant |
| worker pending | 查看 `worker` 日志和 Redis broker；确认 `worker` 容器 running |
| LLM 调用失败 | 先确定 Ollama / LiteLLM / provider 其中一条路径；保留 provider 日志或 curl 证据 |
| 登录失败 | 核对 full-mode 账号来源；不要回退到 `admin/admin` |
| 旧 volume 数据异常 | 先备份，再按 `DEPLOYMENT_RUNBOOK.md` 判断 `docker compose down -v` 或手工补建数据库 |

## 6. R16 验证

命令：

```powershell
docker compose --env-file .env.example config --quiet

$env:XAGENT_SECURITY__JWT_SECRET='0123456789abcdef0123456789abcdef'
$env:LANGFUSE_NEXTAUTH_SECRET='0123456789abcdef0123456789abcdef'
$env:LANGFUSE_SALT='0123456789abcdef0123456789abcdef'
$env:LANGFUSE_INIT_USER_PASSWORD='ChangeMe-R16-Rehearsal-Only-123!'
docker compose --env-file .env.example config --quiet

Get-NetTCPConnection -LocalPort 5432,6379,6333,6334,3001,4000,8080,8081 -ErrorAction SilentlyContinue
```

结果：

- 缺 secret config：退出码 1，报 `required variable LANGFUSE_NEXTAUTH_SECRET is missing a value`。
- 补齐 R16 演练占位 secret 后 config：退出码 0。
- 依赖端口扫描：无输出，表示当前未监听。

## 7. 边界

R16 不做：

- 不启动 compose / full-mode 服务。
- 不创建真实账号或写入 secret。
- 不执行数据库迁移、备份或恢复。
- 不把 `.env.example` 的本地示例值提升为 staging / prod 凭据。
- 不将本清单写成 R4 目标环境演练完成。

R4 仍需基于实际环境执行演练并归档日志、截图、命令输出和异常处置结果。
