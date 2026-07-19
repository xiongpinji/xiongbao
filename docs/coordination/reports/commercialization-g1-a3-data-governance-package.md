# G1-A3 数据 / 权限 / 审计包

> 适用阶段：G1 内部试点可稳定使用
>
> 用途：冻结内部试点阶段的数据边界、权限边界、审计入口与可追责路径，让试点负责人、运维、接手者知道当前能信什么、从哪里回查、哪些默认值不能进入试点环境。

---

## 1. 目标

G1-A3 的目标是：

> **把当前 `xagent` 在内部试点阶段的权限、租户、审计与运行对象回查关系整理成一份可交接的治理包。**

这不是正式商用 GA 的完整合规体系，也不是企业级长期保留策略；它只负责保证：

- 内部试点时权限边界清楚；
- 运行对象能回查；
- 关键 secret 与危险默认值不会被误带入试点；
- 出现问题时能从系统记录追到具体对象。

---

## 2. 权限边界

### 2.1 spine 资源

当前 `spine` 相关能力必须按独立资源理解，而不是继续混用旧 `agent` 语义。

内部试点阶段应明确：

- `viewer`：只能读，不应拥有创建/推进目标任务板的权限；
- `member`：可在受控范围内使用主链能力；
- `admin`：仅用于需要更高权限的环境与配置操作；
- 任何高风险动作都不应依赖默认管理员兜底。

### 2.2 登录模式边界

当前环境分层必须这样理解：

- `lite / dev`
  - 可用于本地开发、页面调试、快速 smoke；
  - 允许 `admin/admin` 这类开发路径存在；
  - 不能作为正式试点或发布凭据证据。
- `full / staging / prod`
  - 必须显式账号来源；
  - 不允许依赖默认管理员；
  - secret 与 JWT 边界必须真实注入。

---

## 3. 运行对象回查关系

内部试点阶段需要明确以下回查链：

- **Goal**：当前交付目标
- **Task**：最小执行单元
- **Run**：一次具体执行实例
- **Workflow**：工作流级运行对象
- **Evidence**：验证 / 交付 / 恢复证据入口

### 3.1 回查入口

- Goal / Task 状态：`/goal-board`
- Run 详情：`/runs/:runId`
- 运行主链与状态迁移：`tests/test_spine_release_flow.py`
- worker / runtime / service 级回查：
  - `tests/test_worker.py`
  - `tests/test_runtime_runs.py`
  - `tests/test_spine_service.py`

### 3.2 对内约定

试点阶段的最小可追责要求是：

1. 能从 Goal Board 找到任务状态；
2. 能从任务状态找到 run id；
3. 能从 run id 打开运行详情；
4. 能从运行详情与相关 evidence 判断失败或成功；
5. 能通过日志 / runbook / 证据入口追到恢复动作。

---

## 4. 审计与证据入口

当前阶段不要求完整企业审计平台，但必须能形成最小可追溯闭环。

### 4.1 当前证据入口

- `docs/coordination/reports/auto-delivery-phase1-report.md`
  - Phase 1 验收报告入口
- `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
  - SQLite / Alembic 漂移诊断与恢复路径
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
  - Chat / SSE / full-flow 主链证据
- `docs/RELEASE_RUNBOOK_V1.md`
  - 发布 / 回滚 / Smoke / 日志保留入口
- `docs/OPERATIONS_MANUAL_V1.md`
  - 巡检、日志、依赖故障与恢复入口

### 4.2 当前最小审计要求

内部试点至少要做到：

- 关键运行对象有唯一 id（task id / run id）；
- 关键失败有对应日志或报告入口；
- 关键恢复动作能在文档中找到执行依据；
- 试点负责人拿到材料后，可以追到“谁发起、谁执行、结果在哪里看”。

---

## 5. 默认值与 secret 边界

### 5.1 当前必须禁止误用的默认值

内部试点阶段必须明确：

- `full` / `staging` / `prod` 不允许依赖 lite 默认 `admin/admin`；
- `JWT secret` 不可为空，不可继续使用危险占位；
- `CORS` 不能使用 `*`；
- 任何正式试点环境都必须显式提供真实 secret。

### 5.2 当前 secret 说明入口

secret 与环境基线统一参考：

- `docs/ENVIRONMENT_BASELINE_V1.md`

其中应作为试点前强制确认项的包括：

- `XAGENT_SECURITY__JWT_SECRET`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_SALT`
- `LANGFUSE_INIT_USER_PASSWORD`
- provider 相关密钥
- 显式账号来源

---

## 6. 最小验证命令

### 6.1 权限 / spine 边界

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_spine_api.py -q
```

预期：
- spine 权限边界相关测试通过；
- `viewer` 不会获得不该有的写权限。

### 6.2 主链回查关系

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_spine_release_flow.py tests/test_runtime_runs.py -q
```

预期：
- task / workflow / run / board 状态链通过；
- run 详情、状态迁移和恢复路径可回查。

### 6.3 worker / service 稳定回查

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_spine_service.py -q
```

预期：
- worker 与 spine service 主链通过；
- 关键运行元数据可被回查。

---

## 7. 完成定义

G1-A3 只有在以下条件同时成立时，才算完成：

- 权限边界可被非开发者解释；
- 试点负责人知道 run / task / workflow / evidence 去哪里查；
- 默认危险值与 secret 边界已经被冻结，不再靠口头补充；
- 当前审计与证据入口足以支持“失败后回查”；
- 不需要深入源码，也能理解内部试点阶段的数据 / 权限 / 审计边界。

---

## 8. 当前结论

G1-A3 的作用不是引入新的权限系统或审计平台，而是：

> **把当前已经存在的数据边界、权限边界、运行回查关系和 secret / 默认值约束，整理成一份内部试点可直接交接的治理包。**

后续若继续推进 G1，应进入：
- `G1-A4 试点交付材料包`
