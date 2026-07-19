# G1-A2 稳定性 / 恢复包

> 适用阶段：G1 内部试点可稳定使用
>
> 用途：冻结内部试点阶段的失败 → 定位 → 恢复最小闭环，让运维、接手者和试点负责人在系统出错时知道应该看哪里、怎么恢复、如何留下证据。

---

## 1. 目标

G1-A2 的目标是：

> **把当前 `xagent` 在内部试点阶段最常见的失败场景、恢复动作和证据入口整理成一个最小可执行包。**

这不是正式商用 GA 的完整发布治理，也不是企业级长期运营手册；它只负责内部试点阶段最需要的稳定性和恢复闭环。

---

## 2. 关键故障类型

当前 G1-A2 需要覆盖的故障类型包括：

1. **任务失败**
   - task 提交成功，但执行进入 failed / recovery
2. **工作流失败**
   - workflow 创建后进入 cancelled / recovery / 等待审批异常
3. **运行详情缺失或异常**
   - run detail、Run Console、SSE/stream 读模型不完整
4. **迁移失败 / 本地库漂移**
   - SQLite / Alembic revision 不一致，或缺表导致主链读写失败
5. **依赖不可用**
   - Postgres / Redis / Qdrant / LiteLLM / Langfuse / worker 等依赖异常

---

## 3. 失败时的观察入口

发生故障时，优先观察下列入口：

### 3.1 Goal Board
- `/goal-board`
- 用于观察当前目标、任务状态、release / recovery 区域
- 重点看任务是否进入 `recovery` 或卡在异常状态

### 3.2 Run 详情 / Run Console
- `/runs/:runId`
- 用于观察运行状态、主要输出、失败信息、恢复线索

### 3.3 健康检查
- `GET /health`
- `GET /ready`
- 用于区分“应用可用但业务失败”和“依赖未就绪/服务未就绪”

### 3.4 容器 / 服务日志
- `docker compose logs --tail=200 api`
- `docker compose logs --tail=200 worker`
- `docker compose logs --tail=200 web`

---

## 4. 最小恢复动作

### 4.1 任务 / 工作流失败

操作顺序：
1. 在 Goal Board 确认任务是否进入 `recovery`
2. 打开对应 `/runs/:runId`
3. 记录失败信息、状态、run id
4. 按运行手册判断是否可直接重试
5. 若属于配置 / 依赖问题，先恢复依赖再重试

### 4.2 运行详情异常 / SSE 完成态异常

优先证据入口：
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`

操作顺序：
1. 确认 `/api/v1/stream/...` 路径是否正常
2. 确认 run id 是否已经同步
3. 若主区不显示结果，先确认是否走到了 fallback / run detail 入口
4. 以 R13 记录的已知修复路径为对照，不在试点现场临时猜测

### 4.3 SQLite / Alembic 漂移

优先证据入口：
- `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`

操作顺序：
1. 判断是否是历史本地 SQLite 漂移库
2. 不把历史漂移库当成正式证据
3. 对 fresh DB 跑 `alembic upgrade head`
4. 需要保留数据时走“备份 → fresh DB → 一次性迁移”路径

### 4.4 依赖不可用

优先看：
- `/ready`
- compose 服务状态
- api / worker 日志

操作顺序：
1. 先看 `docker compose ps`
2. 再看 `/ready`
3. 再看具体依赖日志
4. 恢复依赖后重新执行 smoke / task / workflow 最小路径

---

## 5. 最小演练脚本

G1-A2 至少需要完成一次最小演练，步骤如下：

1. 触发一个可控失败（例如 task 或 workflow 的可解释失败）
2. 在 Goal Board 中观察状态进入 `recovery`
3. 在 `/runs/:runId` 中查看失败详情
4. 按 runbook 恢复依赖或重试
5. 记录：
   - run id
   - 失败截图
   - 日志片段
   - 恢复动作
   - 恢复结果

这次演练的目标不是证明系统永不失败，而是证明：

> **失败后，内部团队知道如何看、如何恢复、如何留下证据。**

---

## 6. 现有证据入口

当前可直接复用的稳定性 / 恢复证据包括：

- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
  - Chat / SSE / full-flow 的主链失败与修复证据
- `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
  - SQLite / Alembic 漂移诊断与恢复指南
- `docs/RELEASE_RUNBOOK_V1.md`
  - 发布、回滚、健康检查、日志采集、Smoke 验证
- `docs/ENVIRONMENT_BASELINE_V1.md`
  - 环境分层、secret、危险默认值禁用策略
- `docs/OPERATIONS_MANUAL_V1.md`
  - 日常巡检、常见告警、最小排障路径

这些材料共同构成当前 G1-A2 的证据基线。

---

## 7. 最小验证命令

### 7.1 后端稳定性主链

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_runtime_runs.py tests/test_spine_service.py -q
```

预期：
- worker、runtime、spine service 主链测试通过
- 失败状态回写、session 决策、任务详情回查稳定

### 7.2 运行主链与 release flow

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_spine_release_flow.py -q
```

预期：
- task / agent / workflow → spine 状态链通过
- recovery / review / release 相关测试通过

### 7.3 基本环境检查

```bash
curl -f http://localhost:8000/health
curl -f http://localhost:8000/ready
curl -f http://localhost:3000
```

预期：
- `/health` 返回 200
- `/ready` 返回 200 且 ready=true
- 前端入口可达

---

## 8. 完成定义

G1-A2 只有在以下条件同时成立时，才算完成：

- 常见失败类型有明确观察入口；
- 至少一条“失败 → 定位 → 恢复”脚本被固定；
- 运行手册、环境基线和诊断证据之间存在明确引用关系；
- 接手者在不问开发者的前提下，也能知道从哪里开始排障；
- 现有恢复材料不再只是散落报告，而是成为试点阶段稳定性包的一部分。

---

## 9. 当前结论

G1-A2 不负责正式商用 GA 的完整发布治理，也不负责企业级长期运营。它只负责：

> **把当前 `xagent` 在内部试点阶段最常见的失败与恢复路径，整理成一份可以真正拿来值守与排障的稳定性 / 恢复包。**

后续若要继续推进 Phase 1，应在此基础上进入：
- `G1-A3 数据 / 权限 / 审计包`
- `G1-A4 试点交付材料包`
