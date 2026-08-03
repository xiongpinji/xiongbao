# 多实例部署指南（Horizontal Scaling）

> 适用场景：在负载均衡器后运行 ≥2 个 `xagent-api` 实例（`full` 模式）。
> 单实例 / lite 模式无需本文档的任何额外配置。

X-Agent 默认假设单进程运行，代码中存在若干**进程内状态**。多实例部署时
必须按下文清单完成外部化，否则会出现限流被绕过、定时任务重复触发、
向量库文件锁冲突、配置漂移等问题。

---

## 1. 必配清单

### 1.1 Redis（必配）——登录限流 + 调度器分布式锁

配置（所有实例指向同一 Redis）：

```bash
XAGENT_CACHE__REDIS_URL=redis://redis:6379/0
```

配置后自动启用：

| 能力 | 行为 |
|---|---|
| 登录限流 | `LoginRateLimiter` 自动切换 `RedisBackend`：失败计数为 Redis 有序集合滑动窗口（key `xagent:login_rl:fail:*`，TTL=窗口），锁定标记 `SET ... PX`（key `xagent:login_rl:lock:*`）。多实例共享计数与锁定，爆破无法靠轮询实例绕过。 |
| 调度器防重 | `Scheduler` 启动时自动创建 `RedisJobLock`：每个 job 触发前 `SET xagent:scheduler:lock:{job_id} {instance} NX PX`，**锁租约 = 调度间隔 × 90%（< 间隔）**，同一轮只有一个实例执行；持锁实例崩溃后锁自然过期，其他实例可接管。 |

降级语义：

- **未配置 Redis**：登录限流为进程内实现（lite/单实例现状）；调度器启动时打
  一次性 warning（`scheduler_no_distributed_lock`）并保持单实例行为。
- **Redis 运行中挂掉**：
  - 登录限流：打 warning（`login_rate_limit_redis_error`）并降级到进程内存计数，
    限流功能不中断，但多实例下计数退化为各实例独立统计。
  - 调度器：打 warning（`scheduler_lock_redis_error`），本轮**不触发**——
    宁可漏触发一轮，也不冒多实例重复执行的风险。

### 1.2 Qdrant Server（必配）——禁用本地磁盘模式

本地磁盘模式（默认 `apps/data/qdrant` 或 `XAGENT_MEMORY__QDRANT_LOCAL_PATH`）
使用**独占文件锁**，多实例同时打开会直接报错。多实例必须使用 Qdrant server：

```bash
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 \
  -v qdrantdata:/qdrant/storage qdrant/qdrant:latest
```

```bash
XAGENT_MEMORY__QDRANT_URL=http://qdrant:6333
# 清空本地路径，避免误用磁盘模式
XAGENT_MEMORY__QDRANT_LOCAL_PATH=
```

`deploy/compose/docker-compose.yml` 已包含 qdrant 服务并接好
`XAGENT_MEMORY__QDRANT_URL`；根 `docker-compose.yml` 也已补充。

### 1.3 数据库（必配）——审计链 / 计费 / Webhook 注册已共享

审计事件、计费、Webhook 注册表等均落共享数据库（Postgres），多实例天然一致，
无需额外配置。注意审计哈希链以 DB 表尾恢复 `seq`/`prev_hash`（见 §3 风险清单）。

### 1.4 负载均衡：SSE / WebSocket 需要 sticky session

- Agent 运行流（`POST /api/v1/agents/run`，SSE）和 `/ws`（WebSocket）是
  **长连接**，连接状态只在单个实例内存中（`ConnectionManager`）。
- 负载均衡器必须开启**会话亲和**（sticky session，按 cookie 或源 IP），
  否则同一会话的后续 HTTP 请求落到其他实例会丢失上下文。
- SSE 已内置心跳防 LB 空闲超时；仍建议 LB 的 idle timeout ≥ 300s。
- WebSocket 的广播只覆盖本实例连接（见 §3 风险清单）。

---

## 2. 共享盘注意事项

| 路径 | 状态 | 多实例建议 |
|---|---|---|
| 定时任务定义 `data/scheduler/*.json` | 文件 | **不要让多个实例挂载同一目录做"共享"**：`next_run` 只在执行实例内存中推进，共享文件反而会造成状态错乱。每个实例用自己的 job 存储 + Redis 分布式锁即可（锁保证同一轮只有一个实例真正执行）。 |
| runtime_config overrides | **纯进程内存，无文件持久化** | 通过 API 修改的 overrides 只作用于处理该请求的实例，重启即丢失。多实例下避免使用运行时配置 API 改关键配置；改用环境变量/`.env` 统一下发并滚动重启。 |
| Qdrant 本地存储 | 独占文件锁 | 见 §1.2，禁用本地模式。 |
| 画布快照 / 草稿（creative-studio） | 进程内存 + 本地快照文件 | 多实例下草稿/画布在实例间不可见，待解决（§3）。 |

---

## 3. 多实例风险清单

### ✅ 已解决（本工作流 S2-3）

| 组件 | 原风险 | 解决方案 |
|---|---|---|
| 登录限流 `enterprise/auth/login_rate_limit.py` | 各实例独立计数，限流可被绕过 | `RedisBackend`（滑动窗口 + PX 锁定），Redis 挂降级内存 + warning |
| 定时调度器 `core/scheduler` | 各实例独立触发，任务重复执行 | `RedisJobLock`（SET NX PX，租约 < 调度间隔），无锁跳过本轮 |
| Qdrant 本地模式 `adapters/memory/qdrant_store.py` | 独占文件锁，多实例启动冲突 | 文档强制 `XAGENT_MEMORY__QDRANT_URL` 指向 server（`qdrant_local_path` 此前已可配） |

### ⚠️ 待解决（已排查，未修复）

| 组件 | 位置 | 风险 | 建议方向 |
|---|---|---|---|
| WebSocket 连接管理 | `api/ws.py` `ConnectionManager` | 在线用户/广播只在单实例内存，跨实例广播丢失 | Redis pub/sub 做跨实例广播 |
| runtime_config overrides | `api/runtime_config.py` | 纯内存 dict，实例间配置漂移、重启丢失 | overrides 落 DB/Redis + 变更事件广播 |
| 媒体任务表 | `api/v1/creative_studio.py`（`_media_runtime_tasks` 等进程内 dict） | 任务状态只在提交实例可见，轮询请求落到其他实例查不到 | 任务状态落 DB（Celery result backend 或专表） |
| 画布/草稿 | `api/v1/canvas.py`、`creative_studio.py` | 进程内存 + 本地快照，实例间不可见 | 落 DB 或共享对象存储 |
| 审计哈希链 | `enterprise/audit/chain.py`（`persist=True` 时从 DB 恢复） | DB 共享后链状态以**表尾**为准；若内存链（`persist=False`）实例各自为链，且 DB 不可用时降级纯内存会导致实例间链不一致 | 强制 `persist=True`（full 模式默认）；审计写失败告警 |
| Webhook 投递 | `core/webhooks.py` `emit()` | 注册表已落 DB 共享，但投递动作由处理事件的实例直接发起；实例崩溃则该次投递丢失（无持久队列/重试） | 投递改走 Celery 任务（broker=Redis，自动重试） |
| 任务租户映射 | `api/v1/tasks.py`（`_task_tenants` 等） | 进程内存映射，实例重启/漂移后丢失 | 落 DB |
| skills 存储 | `core/skills` `SkillStore` | 本地文件目录（compose 中为 named volume） | 多实例挂共享卷或对象存储，只读分发 |

---

## 4. 最小多实例配置样例

```bash
XAGENT_MODE=full
XAGENT_DB__URL=postgresql+asyncpg://xagent:***@postgres:5432/xagent
XAGENT_CACHE__REDIS_URL=redis://redis:6379/0
XAGENT_MEMORY__QDRANT_URL=http://qdrant:6333
XAGENT_SECURITY__JWT_SECRET=<至少 32 字符随机串，所有实例一致>
```

验证清单：

1. 所有实例 `/health` 中 Redis/Qdrant 检查通过；
2. 连续失败登录 5 次（分散打到不同实例）→ 第 5 次后任意实例访问均 429；
3. 创建 1 分钟级定时任务 → 日志中同一轮只有一个实例出现 `job_executing`，
   其余实例出现 `job_skipped_lock_held`；
4. 停掉任一实例 → 任务在下一个周期由存活实例接管（锁租约到期）。
