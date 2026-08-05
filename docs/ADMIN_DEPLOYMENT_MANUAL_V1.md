# X-Agent 管理员部署手册 v1

> 适用对象：客户侧管理员、交付负责人、实施负责人。
>
> 适用范围：当前 `xagent` 单机 / Docker Compose `full` 模式部署。
>
> 边界：本文档用于“管理员如何部署与交接”，**不替代** `docs/RELEASE_RUNBOOK_V1.md` 的发布 / 回滚执行证据，也**不代表** R4 目标环境演练已经完成。

---

## 1. 部署目标

当前候选支持的推荐交付形态是：

- 单机 / Docker Compose `full` 模式；
- 内部试点；
- 受控私有部署；
- 交付后由客户管理员或内部平台团队维护。

当前不在本手册覆盖范围内：

- 多实例 HA；
- 蓝绿 / 金丝雀流量切换；
- K8s 生产级 secretRef 平台化；
- 跨版本大规模数据迁移。

---

## 2. 部署前置条件

## 2.1 基础软件

目标机器至少具备：

- Docker 24+
- Docker Compose v2
- Node.js 20+（用于构建 `apps/web/dist`）
- Git（用于固定候选版本）

## 2.2 端口需求

默认占用端口：

- `3000`：前端入口
- `3001`：Langfuse
- `4000`：LiteLLM
- `5432`：Postgres
- `6379`：Redis
- `6333` / `6334`：Qdrant
- `8000`：X-Agent API
- `8080`：ContextForge
- `8081`：OpenFGA

部署前应确认这些端口未与目标机器既有服务冲突。

## 2.3 候选版本固定

部署必须绑定到唯一候选 commit / 分支 / PR，不得直接使用脏工作树。

至少记录：

- Release ID / 版本号
- Git branch
- Git commit SHA
- 对应 PR
- 对应 CI run URL

若候选未冻结，部署不得进入正式交付签字。

---

## 3. 必填配置与 secret

当前 `full` 模式部署至少要提供以下显式配置：

- `XAGENT_SECURITY__JWT_SECRET`
- `XAGENT_CORS_ORIGINS`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_SALT`
- `LANGFUSE_INIT_USER_PASSWORD`
- 至少一条真实 LLM 路径：
  - `XAGENT_LLM__PROXY_URL` + `XAGENT_LLM__PROXY_API_KEY`，或
  - `XAGENT_LLM__OLLAMA_BASE_URL` + 模型可达，或
  - provider key（OpenAI / DeepSeek）
- `POSTGRES_PASSWORD`（若使用 compose 内置 Postgres）

补充要求：

- `full` / `enterprise` 不允许默认 `admin/admin`；
- `XAGENT_CORS_ORIGINS` 不允许 `*`；
- JWT secret 必须是 32+ 字符随机值；
- staging / prod secret 不得写入 Git。

变量口径与注入方式以 [ENVIRONMENT_BASELINE_V1.md](ENVIRONMENT_BASELINE_V1.md) 为准。

---

## 4. 部署步骤（管理员视角）

### 4.1 获取候选代码

1. 拉取固定候选分支或 tag。
2. 核对 commit SHA 与交付单一致。
3. 核对该候选对应远端 CI 为绿色。

### 4.2 构建前端产物

在仓库根执行：

```powershell
cd apps\web
npm ci
npm run build
```

期望：

- `apps/web/dist` 生成成功；
- 无 lint/typecheck/build 阻断残留；
- 构建失败则停止后续部署。

### 4.3 准备 Compose 环境文件

```powershell
cd ..\..\deploy\compose
Copy-Item .env.example .env
```

然后在 `.env` 中填入真实 secret 与环境值。

最少应核对：

- JWT secret 已填写；
- Langfuse 3 项 secret 已填写；
- LLM 路径可达；
- CORS 来源对齐真实前端域名；
- 若使用 compose 内置数据库，`POSTGRES_PASSWORD` 已覆盖示例值。

### 4.4 做部署前配置校验

```powershell
docker compose --env-file .env config --quiet
```

期望：

- 缺少必填 secret 时直接失败；
- 全部必填项齐全后退出码为 0。

### 4.5 启动服务

```powershell
docker compose up -d --build postgres redis qdrant litellm langfuse
docker compose up -d --build api worker web
docker compose ps
```

期望：

- `api` / `worker` / `web` 为 running；
- `api` 启动阶段执行迁移；
- `api` / `worker` 会尝试执行 warmup；
- `web` 可通过 `http://<host>:3000` 访问。

---

## 5. 部署后最小验收

管理员至少完成：

```powershell
curl.exe -f http://localhost:8000/health
curl.exe -f http://localhost:8000/ready
curl.exe -f http://localhost:3000
```

并记录：

- `/health` 结果
- `/ready` 结果
- `docker compose ps`
- `docker compose logs --tail=200 api worker web`

如果当前环境还没有 full-mode 显式账号，需要先按既定初始化流程创建账号；不得使用 `admin/admin` 作为 full-mode 验收凭据。

---

## 6. 交付给客户管理员时要说明的边界

必须明确说明：

1. 当前推荐交付形态是单机 / Compose `full` 模式；
2. `lite` 只用于本地开发 / demo，不作为正式环境；
3. 正式商用签发仍要求：
   - 候选冻结；
   - 对应远端 CI 绿色；
   - 目标环境 / staging 等价演练证据；
   - 发布 / 回滚归档；
   - 负责人签字；
4. 当前 Helm / K8s 平台化能力不应被口头包装成“已完成生产就绪”。

---

## 7. 交付归档建议

每次部署至少归档：

- Release ID / 版本号
- branch / commit / PR
- CI run URL
- `.env` 来源说明（不要存真实 secret）
- `docker compose config --quiet` 结果
- `docker compose ps`
- `/health` / `/ready` / 前端入口结果
- 登录验收结果
- Run Console 验收结果
- 回滚负责人

发布和回滚的严格执行步骤，统一以 [RELEASE_RUNBOOK_V1.md](RELEASE_RUNBOOK_V1.md) 为准。

---

## 8. 当前结论

这份手册可用于指导当前候选的管理员部署与交付交接。

但请注意：

> **“有手册”不等于“已经完成目标环境演练”。**
>
> 正式交付结论仍取决于 `COMMERCIAL_RELEASE_CHECKLIST_V1.md` 的 gate 是否真实通过。
