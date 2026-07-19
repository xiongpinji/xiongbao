# X-Agent 已知问题与试点边界 v1

> 用途：把当前候选不能回避的已知缺口、试点限制与不支持范围显式写出来，避免交付时口头弱化。
>
> 适用范围：`candidate/min-send-review-20260707-claude` 当前代码线。

---

## 1. 当前一句话边界

当前 `xagent` 可以按：

- **内部试点**
- **受控私有部署**
- **单机 / Compose `full` 模式交付**

来理解。

### 1.1 商用成熟度阶段映射

- 当前激活阶段：**G1｜内部试点可稳定使用**。
- **G2｜正式商用 GA** 未开启，因为还缺版本冻结、目标环境演练、签字闭环。
- **G3｜企业级长期运营** 未开启，因为还缺 HA / K8s / SLO / 审计保留 / 容量边界。
- 当前推进规则：仅 **G1** active；**G2** 仅在 G1 四个 Gate 全部通过后开启；**G3** 仅在 G2 四个 Gate 全部通过后开启。

当前**不能**按以下口径对外承诺：

- 正式商用 GA；
- 多实例 HA 已验证；
- K8s / enterprise secretRef 已完成平台化落地；
- 所有运维、性能、恢复、告警能力都已完成正式签字。

---

## 2. 当前已知问题

## 2.1 目标环境 / full-mode 演练仍是正式交付阻断

截至当前候选，正式交付仍缺：

- `R4` 目标环境 / full-mode 演练证据；
- full-mode 显式账号、Langfuse secret、LLM 路径等真实环境输入；
- 演练日志、截图、结果归档。

因此：

> lite/dev 本地证据不能替代 staging/full 证据。

## 2.2 正式 PR 审查包仍未闭环

当前候选虽已有 PR、已有远端 CI 绿色记录，但正式发布仍不应跳过：

- R4 环境演练证据；
- R5 PR 审查包签发；
- Reviewer 对关键 REVIEW 包的验收。

## 2.3 运维体系仍是“可值守”，不是“全量商用体系已封板”

当前仓库已具备：

- `/health`
- `/ready`
- `/metrics`
- Langfuse 接入点
- Grafana dashboard 文件入口

但当前仍未在正式发布材料中闭环：

- SLO / 告警阈值签字版；
- 恢复演练完成记录；
- 容量基线 / 并发建议签字版。

## 2.4 Helm / K8s 平台化不应被过度承诺

当前 Helm 侧已做安全默认值硬化与 fail-fast，但这不等于：

- 已完成目标平台的 secret manager / secretRef 接入；
- 已完成 K8s 集群级变更窗口治理；
- 已完成企业级多实例演练。

## 2.5 支持范围优先围绕 Compose full 模式

当前最稳妥的交付形态是：

- 单机 / Compose `full`
- 内部试点 / 受控私有部署

不建议把以下能力作为当前默认交付承诺：

- 大规模多租户 SaaS 级承载；
- 多地域高可用；
- 大规模并发容量承诺；
- 跨版本兼容承诺。

---

## 3. 当前支持范围

当前推荐支持：

- 单机 / Docker Compose 部署；
- API / worker / web 同步升级；
- Postgres / Redis / Qdrant / LiteLLM / Langfuse 配套启动；
- 登录、运行、Run Console 最小主链；
- internal pilot / controlled delivery。

---

## 4. 当前不支持或不应默认承诺的范围

以下范围当前不应默认承诺给交付对象：

- 多实例 HA；
- 蓝绿 / 金丝雀发布治理；
- 企业级 K8s secretRef / external secret manager 已实装；
- 完整容量压测结论；
- 完整 RTO / RPO 承诺；
- 桌面壳打包 / 签名 / 分发已完成；
- 所有 enterprise 接入点都已做客户现场验证。

---

## 5. 试点交付时必须提前说明的限制

试点前应明确告知：

1. 当前候选更适合受控范围验证，不适合无限制扩容；
2. full-mode 环境需要显式配置 secret 与账号，不提供默认管理员；
3. 若现场环境无法提供 LLM 路径、Langfuse secret 或依赖服务，则无法视为交付失败前的同级环境；
4. 如需 K8s / enterprise 平台化落地，应拆为后续专项工作，而不是从当前候选口头外推。

---

## 6. 发布判定建议

### 可以成立

- 内部试点可交付
- 受控私有部署可交付
- 发布前审查准备可继续推进

### 当前不能成立

- 正式商用 GA
- 所有发布阻断项清零
- 所有环境演练完成
- 所有交付角色已签字

---

## 7. 与其他文档的关系

- 真实状态：[`COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`](COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md)
- 发布门禁：[`COMMERCIAL_RELEASE_CHECKLIST_V1.md`](COMMERCIAL_RELEASE_CHECKLIST_V1.md)
- 发布 / 回滚：[`RELEASE_RUNBOOK_V1.md`](RELEASE_RUNBOOK_V1.md)
- 环境与 secret：[`ENVIRONMENT_BASELINE_V1.md`](ENVIRONMENT_BASELINE_V1.md)
- 最终收尾口径：[`coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`](coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md)

---

## 8. 当前结论

这份文档的目的不是放大风险，而是防止交付时把“试点可交付”说成“正式商用已完成”。

> **当前候选可用于试点与受控交付，但正式交付仍取决于环境演练、PR 审查包和最终签字是否真实闭环。**
