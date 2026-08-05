# X-Agent Release Runbook v1

> 用途：给 `xagent` PR 审查准备、内部试点、staging 或受控私有部署提供发布 / 回滚执行步骤。
>
> 本文档不是正式商用发布结论。正式发布仍必须满足 `COMMERCIAL_RELEASE_CHECKLIST_V1.md` 中的 P0 阻断项、远端 CI 全绿、目标环境演练和 Owner 签字。

---

## 1. 适用范围

本 runbook 覆盖：

- 单机 / Docker Compose full 模式发布。
- 本地或 staging 环境的 release rehearsal。
- API / worker / web 同步升级。
- Postgres schema 迁移、基础备份、回滚和 smoke。

暂不覆盖：

- 多实例 HA、蓝绿 / 金丝雀流量切换。
- K8s 生产集群的完整变更窗口治理。
- 企业 SSO 用户初始化的客户侧流程。
- 数据大规模迁移、跨版本兼容承诺。

---

## 2. 发布输入

发布前必须填写以下信息，并在交付报告或 PR 描述中保留：

| 字段 | 值 |
|---|---|
| Release ID / 版本号 | 待填 |
| Git commit / tag | 待填 |
| 发布环境 | dev / staging / prod |
| 发布负责人 | 待填 |
| 回滚负责人 | 待填 |
| 变更窗口 | 待填 |
| 数据备份路径 | 待填 |
| CI run 链接 | 待填 |
| E2E / smoke 证据链接 | 待填 |

发布包不得把未冻结、未提交或未进入候选分支的工作树内容当成交付内容。

---

## 3. 发布前 Gate

### 3.1 代码与 CI

必须满足：

- 当前候选分支 / tag 已固定。
- 当前候选对应的远端 CI 全绿。
- PR 描述包含风险、验证矩阵、回滚策略和 reviewer 关注点。
- 本地工作树未混入发布外改动。

推荐记录命令：

```powershell
git rev-parse HEAD
git status --short
gh run list --branch <release-branch> --limit 5
gh pr checks <pr-number>
```

若远端 CI 不是当前候选提交的结果，不能作为发布 gate 证据。

### 3.2 本地质量门禁

在仓库根目录运行：

```powershell
$env:PYTHONPATH = "$PWD\apps\api"
$env:PYTHONIOENCODING = "utf-8"
.\apps\api\.venv\Scripts\python.exe -X utf8 -m ruff check apps\api\xagent apps\api\tests
.\apps\api\.venv\Scripts\python.exe -X utf8 -m pytest -q apps\api\tests

cd apps\web
npm ci
npm run lint
npm run typecheck
npm run build
```

关键 Playwright E2E 必须至少有一组通过证据。当前 R3 的 `creative-smoke.spec.ts` 可作为 lite/dev 关键路径证据；full / staging / prod 不得使用默认 `admin/admin` 作为正式发布凭据证据。

### 3.3 环境与 secret

环境基线、变量清单和 secret 注入方式见 `docs/ENVIRONMENT_BASELINE_V1.md`。

发布环境必须显式提供：

- `XAGENT_SECURITY__JWT_SECRET`
- `XAGENT_CORS_ORIGINS`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_SALT`
- `LANGFUSE_INIT_USER_PASSWORD`
- LLM provider 配置：OpenAI / DeepSeek / Ollama / LiteLLM 至少一条可用路径
- full / enterprise 登录账号来源：Keycloak / DB / 显式初始化流程

生产或 staging 不允许依赖 lite 默认 `admin/admin`。

---

## 4. 构建与配置校验

### 4.1 前端构建

```powershell
cd apps\web
npm ci
npm run build
```

期望：

- `apps/web/dist` 已生成。
- 构建失败时停止发布，不继续 compose 部署。

### 4.2 Compose 配置校验

```powershell
cd deploy\compose
Copy-Item .env.example .env
# 编辑 .env，填入真实 secret 和环境地址
docker compose --env-file .env config --quiet
```

期望：

- 缺少必填 secret 时命令失败。
- 提供真实 secret 后命令退出码为 0。

---

## 5. 数据备份与 DB 迁移

### 5.1 备份

发布前至少备份 Postgres。PowerShell 示例：

```powershell
cd deploy\compose
New-Item -ItemType Directory -Force backups | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
docker compose exec -T postgres pg_dump -U xagent xagent > "backups\xagent-$stamp.sql"
```

如本次环境使用 Qdrant 持久化数据，还应在 Qdrant 控制面或 API 中创建 collection snapshot，并记录 snapshot 路径。

### 5.2 迁移

Compose 的 `api` 服务启动命令会执行 `python -m alembic upgrade head`。发布执行时仍建议在启动应用前显式跑一次迁移：

```powershell
cd deploy\compose
docker compose up -d postgres redis qdrant
docker compose run --rm api python -m alembic current
docker compose run --rm api python -m alembic upgrade head
docker compose run --rm api python -m alembic current
```

期望：

- `upgrade head` 退出码为 0。
- `current` 输出为仓库当前 Alembic head。
- 迁移失败时立即停止发布，保留日志，并按第 8 节回滚或恢复备份。

---

## 6. 发布步骤

```powershell
cd deploy\compose
docker compose up -d --build postgres redis qdrant litellm langfuse
docker compose up -d --build api worker web
docker compose ps
```

期望：

- `api`、`worker`、`web` 均处于 running。
- `api` 启动日志无配置校验失败、迁移失败、JWT secret 缺失或 CORS 危险配置错误。
- `worker` 能连接 Redis broker。

保留日志：

```powershell
docker compose logs --tail=200 api > release-api.log
docker compose logs --tail=200 worker > release-worker.log
docker compose logs --tail=200 web > release-web.log
```

---

## 7. 发布后 Smoke

### 7.1 健康检查

```powershell
curl.exe -f http://localhost:8000/health
curl.exe -f http://localhost:8000/ready
curl.exe -f http://localhost:3000
```

期望：

- `/health` 返回 200。
- `/ready` 返回 200 且 `ready=true`。
- 前端入口返回 200。

### 7.2 登录与 Run Console

使用当前环境显式初始化的账号登录。不得在 full / prod 使用默认 `admin/admin` 作为验收凭据。

最小人工路径：

1. 打开 `http://localhost:3000`。
2. 登录。
3. 进入「对话」或「工作流」提交一次运行。
4. 页面跳转或手动打开 `/runs/:runId`。
5. 确认 Run Console 展示概览、Timeline、验证 / 风险 / 恢复或 Replay 信息。

### 7.3 自动 smoke

本地或容器内至少执行一组：

```powershell
cd apps\api
$env:PYTHONPATH = "$PWD"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -X utf8 -m xagent.cli smoke
```

Compose 容器内：

```powershell
cd deploy\compose
docker compose exec -T api python -m xagent.cli smoke
```

Playwright 关键 E2E：

```powershell
cd tests\e2e
$env:E2E_BASE_URL = "http://localhost:3000"
npx playwright test specs/creative-smoke.spec.ts --project=chromium
```

若目标环境不允许默认账号，必须先完成 E2E 账号参数化或改用人工登录验收记录；不能把 lite/dev 默认账号结果冒充为 prod 证据。

---

## 8. 回滚步骤

### 8.1 无 DB 迁移或迁移兼容

```powershell
git checkout <previous-release-tag-or-commit>
cd apps\web
npm ci
npm run build

cd ..\..\deploy\compose
docker compose up -d --build api worker web
docker compose ps
```

回滚后重复第 7 节 smoke。

### 8.2 需要恢复 DB

先停止写入服务：

```powershell
cd deploy\compose
docker compose stop api worker web
```

恢复 Postgres 备份：

```powershell
docker compose exec -T postgres dropdb --if-exists -U xagent xagent
docker compose exec -T postgres createdb -U xagent xagent
Get-Content backups\<backup-file>.sql | docker compose exec -T postgres psql -U xagent xagent
```

然后切回上一版本并启动：

```powershell
git checkout <previous-release-tag-or-commit>
cd ..\..\apps\web
npm ci
npm run build

cd ..\..\deploy\compose
docker compose up -d --build api worker web
```

如 Qdrant 数据属于本次变更影响范围，同步按已记录 snapshot 恢复。

### 8.3 回滚验收

回滚成功必须记录：

- 回滚开始 / 结束时间。
- 回滚 commit / tag。
- 是否恢复 DB。
- `/health`、`/ready`、前端入口结果。
- 至少一次核心链路 smoke 结果。
- 未恢复的用户影响和后续处置人。

---

## 9. 异常处置入口

| 现象 | 立即动作 | 证据 |
|---|---|---|
| `docker compose config` 失败 | 检查 `.env` 缺失 secret；不得临时改回弱默认值 | 命令输出 |
| DB 迁移失败 | 停止发布；保留 `api` / Alembic 日志；判断是否恢复备份 | 迁移日志、备份路径 |
| `/ready` 503 | 查看 readiness `components`，定位 DB / Redis / Qdrant | `/ready` 响应、容器日志 |
| 登录失败 | 确认 full 环境账号来源、OIDC/JWKS、JWT secret | `/api/v1/auth/login` 响应、后端日志 |
| Run Console 404 | 检查 `/api/v1/runs/:run_id`、`agent_tasks`、`workflow_runs` | API 响应、DB 查询 |
| worker 任务 pending | 检查 Redis broker、worker 日志、`agent_tasks.status` | worker 日志、任务 ID |
| LLM 调用失败 | 检查 LiteLLM / provider key / Ollama 可达性 | provider 日志、请求 ID |
| 前端空白页 | 检查 `apps/web/dist`、web 日志、浏览器控制台 | web 日志、截图 |

超过变更窗口或关键链路不可用时，执行第 8 节回滚，不继续扩大排查范围。

---

## 10. 证据归档模板

发布或演练完成后，在 `docs/coordination/reports/delivery-report.md` 或 PR 描述中补：

```text
Release ID:
Commit / tag:
环境:
发布负责人:
构建命令与结果:
迁移命令与结果:
备份路径:
/health 结果:
/ready 结果:
登录验收:
Run Console 验收:
E2E / smoke 命令与结果:
日志路径:
回滚是否演练:
剩余风险:
最终结论: 可进入 PR 审查准备 / 可内部试点 / 不可发布
```

`最终结论` 只能基于当次证据填写；没有远端 CI、环境演练或 Owner 签字时，不得写成“正式商用可交付”。
