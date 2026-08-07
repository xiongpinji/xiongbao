# X-Agent Web/API R2 本机隔离 Full Compose 设计

> 日期：2026-08-07
>
> 状态：Owner 已批准方案 A，待规格复核后进入实施
>
> 基线：`feature/webapi-release-hardening` / `0627747`

## 1. 目标

把 R1 已验证的 Web/API 本地发布候选放入生产等价的单实例环境，完成真实内部试用、持久化、恢复、观测和回退演练，使它具备安全部署和持续测试条件。

R2 不是重新实现 R1 功能，也不以“容器成功启动”作为完成。完成必须证明同一套当前源码经过：

1. 隔离 Full 模式编排和最新 PostgreSQL migration；
2. Web → API → PostgreSQL/Redis/Qdrant → 本地真实 Ollama 的同链调用；
3. API/worker/整套服务重启后的状态恢复；
4. 数据备份后在全新隔离实例恢复；
5. 浏览器、服务、指标、故障恢复和回退证据闭环。

## 2. 范围边界

### 2.1 本阶段包含

- PostgreSQL、Redis、Qdrant、API、Celery worker、Nginx Web 的单机 Full 模式核心栈。
- 宿主机 Ollama 作为零付费真实模型入口。
- Platform MCP 的独立验收 profile。
- Prometheus、Grafana 的独立观测 profile。
- 本机强密码、精确 CORS、仅 loopback 暴露、配置预检和健康门禁。
- 数据卷、工作区、技能包、运行产物的持久化与备份/恢复。
- 注册/登录、对话与 run、开发任务、调度器、技能包、会话/checkpoint 的真实浏览器试用。
- 当前分支的测试、镜像、运行日志、截图和审计报告。

### 2.2 本阶段不包含

- 短剧业务及其媒体生成、画布、剪辑和供应商链路。
- Tauri 桌面端、桌面签名、自动更新和桌面发布物。
- 多机 HA、负载均衡、跨节点 sticky session。
- E2B、云托管 sandbox、客户现场异构环境演练。
- 付费模型供应商调用和生产环境写入。
- 正式 push、tag、GitHub Release 或生产部署。

shell/python 工具在 R2 核心栈中保持关闭。本阶段不向 API 容器挂载宿主机 Docker Socket；这避免为了本地试运行引入等同宿主机 root 的控制面。

## 3. 已确认的本机条件

2026-08-07 的设计前只读检查确认：

- Docker Engine/Client `29.5.3`，Docker Compose `5.1.4` 可用。
- 已有其他项目占用宿主机 `5432`，因此不能复用当前固定端口。
- R2 候选端口 `13002/15432/16333/16334/16379/18000/18080/19090` 均空闲。
- Ollama 监听 `127.0.0.1:11434`，已有 `qwen3:4b` 和 `xagent-qwen3:latest`。
- 当前工作树干净，且已是 Git linked worktree；R2 复用该隔离工作树，不创建嵌套 worktree。

这些结果只用于确定设计可行性。正式验收必须重新运行预检，不能把本节当作运行证据。

## 4. 当前编排缺口

`deploy/compose/docker-compose.yml` 已接入主要服务，但还不能直接作为 R2 验收入口：

1. 顶层固定 `name: xagent`，端口固定为常见端口，会与现有项目冲突。
2. ContextForge、OpenFGA、LiteLLM、Langfuse 默认进入启动集合，扩大核心路径故障面。
3. API 和 worker 未显式挂载共享工作区、技能包/产物数据卷，容器替换后文件型状态可能丢失。
4. API 健康检查只验证 `/health`，没有把数据库、Redis 和 Qdrant 深度就绪作为验收门禁。
5. worker 禁用了健康检查，无法区分“容器存在”和“能够消费任务”。
6. Web/API 部分端口绑定所有接口，不符合本机隔离试运行边界。
7. `.env.staging` 与当前 Compose 数据库名和安全要求存在漂移，不能作为 R2 输入。
8. 根目录和 `deploy/compose` 同时存在宣称生产用途的编排入口，容易产生事实源分叉。

## 5. 选定方案与取舍

Owner 选择方案 A：本机隔离核心 Full Compose。

- 未选择“全部扩展服务一次启动”：它会把网关、联邦授权和 tracing 的第三方初始化问题混入核心发布判定。
- 未选择“Web/API 跑宿主机、数据层跑容器”的混合模式：它与实际镜像运行方式不同，重启和恢复证据不足。
- 选定方案以六个核心服务为默认启动面，扩展能力通过 profile 分批验收；既保持生产等价容器边界，也限制本轮复杂度。

## 6. 目标架构

```text
Browser 127.0.0.1:18080
  └─ Nginx Web
       └─ X-Agent API :8000（宿主映射 127.0.0.1:18000）
            ├─ PostgreSQL :5432（宿主映射 127.0.0.1:15432）
            ├─ Redis :6379（宿主映射 127.0.0.1:16379）
            ├─ Qdrant :6333/:6334（宿主映射 127.0.0.1:16333/:16334）
            └─ host.docker.internal:11434 / qwen3:4b

Celery worker
  ├─ PostgreSQL
  ├─ Redis
  ├─ Qdrant
  ├─ shared workspace/artifact volume
  └─ host.docker.internal:11434 / qwen3:4b

Profiles
  ├─ mcp: Platform MCP
  ├─ observability: Prometheus + Grafana
  ├─ gateway: LiteLLM（本阶段不验收）
  ├─ tracing: Langfuse（本阶段不验收）
  └─ federation: ContextForge + OpenFGA（本阶段不验收）
```

### 6.1 单一事实源

R2 只以 `deploy/compose/docker-compose.yml` 为发布等价编排事实源。根目录 Compose 保留给开发兼容，但文档必须明确其非 R2/发布入口；不新增第三份 Compose。

Compose project name 由 `COMPOSE_PROJECT_NAME` 或命令行显式指定，R2 默认使用 `xagent-r2`。所有宿主端口均可由环境变量覆盖，并默认只绑定 `127.0.0.1`。

### 6.2 服务分层

默认启动：

- `postgres`
- `redis`
- `qdrant`
- `api`
- `worker`
- `web`

R2 验收时再依次启用：

- `mcp`
- `observability`

LiteLLM、Langfuse、ContextForge、OpenFGA 只做 profile 化和 Compose 配置有效性检查，不把它们的运行结果计入 R2 完成声明。

## 7. 配置与秘密管理

新增可提交的 R2 示例配置，只包含非秘密默认值和必填项说明。真实本机配置使用被 `.gitignore` 覆盖的文件，不能进入 Git、日志、截图或证据正文。

预检必须拒绝：

- 空密码或已知默认密码；
- 少于 32 字符的 JWT secret；
- Full 模式下 `CORS=*`；
- 端口被占用；
- Docker/Ollama 不可访问；
- Ollama 目标模型不存在；
- 同名 Compose project 正在使用不兼容配置；
- 当前 Git 工作树不是预期分支或存在未说明修改。

Full 模式保持 `require_auth=true`。不内置 `admin/admin`，试用账号通过 `/api/v1/auth/register` 创建，并使用隔离 tenant。

## 8. 数据与持久化

保留独立 named volumes：

- PostgreSQL 数据；
- Redis AOF；
- Qdrant collection；
- Grafana/Prometheus 数据；
- X-Agent 共享数据。

API 和 worker 共享 X-Agent 数据卷，并显式设置：

```text
XAGENT_WORKSPACE=/data/workspace
XAGENT_STORAGE__LOCAL_ROOT=/data/storage
```

数据库保存业务记录、租户、run、scheduler、checkpoint 和审计元数据；共享文件卷保存 Git 工作区、技能包文件、patch、证据归档及其他文件产物。两者必须在备份/恢复中保持版本一致。

### 8.1 备份与恢复

备份集合至少包含：

- PostgreSQL 逻辑备份；
- Redis 持久快照/AOF；
- Qdrant snapshot；
- X-Agent 共享数据卷归档；
- 当前镜像 tag、migration revision、Git commit 和配置摘要，不包含 secret 值。

恢复必须使用新的 Compose project name、全新 volumes 和另一组端口。原 R2 实例保持可回退，不执行 `down -v` 或覆盖式恢复。

## 9. 健康、错误与恢复语义

### 9.1 启动门禁

依赖顺序必须由健康状态控制：

1. PostgreSQL、Redis、Qdrant 健康；
2. migration 到 head；
3. API `/health`、`/health/ready`、`/health/deep` 满足预期；
4. worker 能响应 Celery ping 或完成一项无副作用探针任务；
5. Web 反向代理 API 成功；
6. MCP/观测 profile 分别健康。

Ollama warmup 失败不能被当作真实模型验收成功。即使服务允许降级启动，R2 证据也必须记录真实模型请求和响应。

### 9.2 故障注入

只做可恢复、非破坏性故障：

- 暂停/重启 worker，确认任务状态不会静默丢失或重复完成；
- 暂停/重启 Redis，确认 API 返回可解释失败并在恢复后重新就绪；
- 重启 API，确认登录外持久业务状态仍可读取；
- 重启整套核心栈，确认数据卷和文件产物恢复。

每次注入前记录目标容器和基线状态；不删除 volumes，不影响工作区外服务。

## 10. 内部真实试用路径

所有浏览器验收都从 `http://127.0.0.1:18080` 进入，并通过 Nginx `/api` 反代，禁止测试页面直连另一个 API 实例。

必须完成：

1. 注册隔离账号、登录、刷新后会话保持。
2. 使用本地 `qwen3:4b` 发起对话并创建成功 run。
3. 打开 Run Console，核对事件、证据、checkpoint 和终态。
4. 创建开发任务，验证 Git 结果、review、download/export；高风险 apply 只在临时验收仓库执行。
5. 创建 scheduler job，观察 worker 消费、暂停、恢复和 run history。
6. 导入包含 `SKILL.md`、`references/`、`scripts/`、`assets/` 的测试技能包，重启后仍可读取。
7. 从 checkpoint 恢复为新 run，验证父子关系和刷新后的会话恢复。
8. 启用 Platform MCP，读取同一租户的会话/run/审批/事件，并验证跨租户拒绝。
9. 在桌面宽度和约 1037px 视口完成关键页面检查，浏览器控制台无错误。

短剧路由、桌面端和媒体供应商不出现在本阶段试用矩阵中。

## 11. 观测与审计

Prometheus 必须抓取当前 R2 API，而不是宿主机或历史容器。Grafana 数据源和仪表盘必须指向同一 Prometheus。

验收至少观察：

- API 请求量、错误率、延迟；
- run 成功/失败与执行时长；
- scheduler claim/retry/recovery；
- worker 在线状态；
- PostgreSQL、Redis、Qdrant 深度健康；
- Ollama 调用失败或超时；
- 浏览器 client error 上报。

日志和审计导出必须脱敏 token、JWT secret、数据库密码及外部 key。

## 12. 实施阶段

### R2-A：编排硬化

- 参数化 project name、loopback 端口和数据库名。
- 为扩展服务增加 profiles。
- 增加共享数据卷、环境变量和健康依赖。
- 提供安全示例配置和 PowerShell 预检入口。
- 明确唯一 R2 Compose 入口。

### R2-B：核心栈与真实模型

- 重新构建当前 HEAD 镜像。
- fresh volumes 启动核心栈并执行 migration。
- 验证深度健康、worker 和 Ollama。
- 完成核心浏览器内部试用。

### R2-C：恢复、观测与 MCP

- 重启和故障注入。
- 启用 observability 与 mcp profiles。
- 完成备份并恢复至新的隔离 project。
- 在恢复实例重复关键读取和浏览器验收。

### R2-D：发布审计

- 后端全量测试、Web 测试/typecheck/lint/build/audit。
- Compose config、镜像、migration、健康、浏览器与恢复证据汇总。
- 更新任务板、运行手册和 R2 证据报告。
- 只形成“可进入人工部署审批”的结论，不执行 push/tag/deploy。

## 13. 完成标准

R2 只有同时满足以下条件才能标记完成：

1. 当前 HEAD 的核心 Full Compose 在隔离 project/ports/volumes 中从零启动。
2. 最新 migration 为 `20260807_checkpoints` 或实施时仓库中的更新 head。
3. `/health`、ready、deep health、worker、Web proxy 均有新鲜证据。
4. 至少一次真实本地 Ollama 请求完成，不能使用 MockLLM 替代。
5. 第 10 节的核心浏览器路径通过，控制台和服务日志无未解释错误。
6. API、worker、整栈重启后持久状态和文件产物仍可读取。
7. 备份已在全新隔离实例恢复，并重复验证账号、会话、run、scheduler、skill 和 checkpoint。
8. MCP 租户边界、Prometheus 抓取和 Grafana 数据源通过。
9. 后端/Web/发布依赖门禁通过；任何 skip、warning、豁免均被准确列出。
10. 证据报告明确已验证、未验证和排除项，且没有生产动作。

任一链路只通过单元测试、Mock、静态页面、历史报告或容器启动，都只能记为部分完成，不能替代 R2 验收。

## 14. 回退与停止条件

- 所有运行使用 R2 专用 project name 和 volumes；停止默认保留数据。
- 回退优先停用 R2 project 并重新启动上一已验证镜像，不修改其他项目容器。
- migration 或恢复失败时保留源实例和备份，不在原 volume 上反复覆盖。
- 若发现需要生产凭据、付费调用、Docker Socket、远程部署或用户数据写入，立即停止并重新取得授权。
- 若真实模型、浏览器、恢复或深度健康任一关键链无法形成证据，最终结论必须标为部分完成或阻塞。
