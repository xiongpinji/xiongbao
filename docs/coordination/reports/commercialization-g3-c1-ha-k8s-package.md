# G3-C1 HA / K8s 包

> 适用阶段：G3 企业级长期运营
>
> 用途：把 `xagent` 从“单机 / Compose 可发布”推进到“可面向企业长期运行的 HA / K8s 方向”时，先固定目标、边界、验证口径和最小通过标准，再决定后续实现深度。

---

## 1. 目标

G3-C1 的目标是：

> **为 `xagent` 建立企业级长期运营的 HA / K8s 路线起点，确保后续多实例、平台化和 secret 管理演进有统一方向。**

这一步不要求立即完成完整 K8s 平台化，但必须明确：

- 多实例验证要验证什么；
- K8s / secretRef / external secret manager 的目标形态是什么；
- 哪些一致性问题必须在扩展前先识别；
- 什么才算“企业级长期运营阶段已真正开始”。

---

## 2. 当前基础

当前已具备的基础包括：

- 单机 / Docker Compose `full` 模式的发布、回滚、演练口径已形成；
- 环境基线与 secret 基线已经文档化；
- `Helm values` 已存在最小 chart 入口；
- 正式商用 GA 的候选冻结、目标环境演练、发布 / 回滚、签字 / 证据包已形成；
- 当前 `full` 模式中 API / worker / web / Postgres / Redis / Qdrant / LiteLLM / Langfuse 等依赖关系已明确。

当前可直接作为 G3-C1 输入的材料：

- `docs/ENVIRONMENT_BASELINE_V1.md`
- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `deploy/helm/values.yaml`
- `deploy/compose/docker-compose.yml`
- `docs/coordination/reports/commercialization-goal-board.md`

---

## 3. 当前缺口

### 3.1 多实例验证缺口

当前仍未证明：
- API 多副本是否可以稳定工作；
- worker 多副本是否会带来重复消费 / 幂等问题；
- Goal / Task / Run / Workflow 在多副本下是否还能保持可追溯一致性。

### 3.2 K8s 平台化缺口

当前仍未证明：
- Helm chart 是否已经能表达正式长期运行所需的 secret 管理方式；
- 是否支持 `secretRef` / external secret manager 方向；
- 是否已经具备集群级变更窗口的最小治理边界。

### 3.3 一致性与状态缺口

当前仍未证明：
- task / workflow / run 状态链在多副本下的幂等性；
- cache / queue / DB / vector store 的一致性前提是否被满足；
- 回滚后多实例状态是否能收敛。

---

## 4. 本包要回答的四个问题

G3-C1 的核心不是“立刻上线 K8s”，而是先回答：

1. **是否以 K8s 作为主平台方向？**
2. **secret 注入从 env 过渡到 secretRef / external secret manager 的目标形态是什么？**
3. **多实例下哪些组件必须先证明幂等 / 一致性？**
4. **企业级长期运营阶段的最小 HA 通过标准是什么？**

---

## 5. 最小验证口径

### 5.1 Helm / K8s 渲染验证

至少验证：

```powershell
helm template xagent deploy/helm --set api.enabled=true --set security.jwtSecret=<32+ chars random>
```

目标：
- chart 能渲染；
- `jwtSecret` 仍 fail-fast；
- 不把危险默认值带入平台化方向。

### 5.2 多实例结构检查

最少应明确：
- API 可以设 `replicaCount > 1`
- worker 可以设 `replicas > 1`
- autoscaling 已有最小入口
- 但这些并不等于“HA 已验证通过”

### 5.3 secret 管理方向检查

必须明确：
- 当前是 env / values 注入
- 后续目标是 secretRef / external secret manager
- 在完成平台化任务前，不得把“已支持 secretRef”写成已完成事实

---

## 6. 最小通过标准

G3-C1 要通过，至少需要满足：

1. HA / K8s 方向已经被正式确认为企业级长期运营的首个执行包；
2. Helm / K8s / secretRef / external secret manager 的目标方向已明确；
3. 多实例前必须验证的一致性边界已被列出；
4. 团队已经知道后续不是“随便开副本”，而是要按一致性验证和 secret 管理升级路径推进。

这意味着：
- G3-C1 的“通过”不是平台化已经完成；
- 而是平台化的目标、边界、验证口径已经冻结。

---

## 7. 当前结论

G3-C1 的作用不是马上把项目变成 K8s 平台，而是：

> **把企业级长期运营阶段的 HA / K8s / secret 管理 / 多实例一致性方向正式冻结下来，作为 G3 的第一个执行包。**

完成 G3-C1 后，下一步最自然的包是：
- `G3-C2 可观测 / 告警包`
