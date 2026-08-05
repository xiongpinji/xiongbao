# G3-C2 可观测 / 告警包

> 适用阶段：G3 企业级长期运营
>
> 用途：冻结 `xagent` 在企业级长期运营阶段需要的可观测入口、关键指标、日志/Trace 入口与告警方向，确保后续长期运行不再依赖“用户先报错我们才知道”。

---

## 1. 目标

G3-C2 的目标是：

> **把长期运营阶段的指标、日志、Trace、告警与关键运行信号冻结成一个可执行包，为后续真正的运维体系落地提供明确边界。**

这一步不要求立刻建成完整监控平台，但必须明确：

- 当前有哪些观测入口；
- 哪些信号是必须关注的；
- 哪些告警阈值至少要定义；
- 哪些角色负责看这些信号。

---

## 2. 当前已有基础

当前已经具备的基础包括：

- `/health`
- `/ready`
- `/metrics`
- Langfuse 接入点
- Grafana dashboard 文件入口
- Run Console / Goal Board 运行态入口
- worker / api / web 日志入口

并且已有材料：

- `docs/OPERATIONS_MANUAL_V1.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`
- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/coordination/reports/commercialization-goal-board.md`

---

## 3. 当前缺口

### 3.1 指标层缺口

当前虽然已有 `/metrics`，但仍未冻结：
- 哪些指标是正式长期运营必须看的；
- 哪些指标对应性能、错误率、队列积压、就绪抖动；
- 哪些指标达到阈值时需要响应。

### 3.2 日志 / Trace 缺口

当前已有日志与 Langfuse 接入点，但仍未冻结：
- 哪些问题优先看日志；
- 哪些问题优先看 Trace；
- 哪些日志关键字算高风险信号；
- Trace / Langfuse 在长期运营中由谁负责维护。

### 3.3 告警层缺口

当前仍未冻结：
- P95 / 错误率 / 429 / 402 / worker backlog 等指标的最小阈值；
- 哪些异常属于“立即响应”；
- 哪些异常可以进入缺陷池。

---

## 4. 当前必须关注的关键观测点

### 4.1 健康与就绪
- `/health`
- `/ready`

### 4.2 worker / backlog
- worker 运行状态
- 任务长期 pending
- broker / Redis 健康

### 4.3 API / 前端主链
- 登录失败率
- run / workflow 失败率
- Run Console / detail 读取异常

### 4.4 LLM / 外部依赖
- provider 401 / 403 / timeout
- `ollama_warmup_failed`
- LiteLLM / Langfuse 可达性

---

## 5. 最小告警方向

G3-C2 至少要把以下方向冻结：

1. **可用性告警**
   - `/health` 失败
   - `/ready` 不通过

2. **主链失败告警**
   - login / run / workflow 大面积失败
   - worker 长时间 pending

3. **依赖退化告警**
   - Postgres / Redis / Qdrant / LiteLLM / Langfuse 不可用

4. **性能退化告警**
   - P95 超阈值
   - backlog 持续攀升
   - 冷启动 / warmup 异常

---

## 6. 最小通过标准

G3-C2 要通过，至少需要满足：

1. 当前可用的指标 / 日志 / Trace 入口已经冻结；
2. 必须看的关键运行信号已经列出；
3. 告警方向已经明确，不再停留在“以后再看”；
4. 团队已经知道长期运营阶段看板和告警大致应该长什么样。

这意味着：
- G3-C2 的“通过”不是 Grafana / Alertmanager 已经全部生产落地；
- 而是长期运营所需的可观测面已经有了清晰定义。

---

## 7. 当前结论

G3-C2 的作用不是立刻建设全量监控平台，而是：

> **把企业级长期运营阶段需要观察什么、在哪里看、什么信号算危险，正式冻结成一个可执行包。**

完成 G3-C2 后，下一步最自然的包是：
- `G3-C3 审计 / 保留策略包`
