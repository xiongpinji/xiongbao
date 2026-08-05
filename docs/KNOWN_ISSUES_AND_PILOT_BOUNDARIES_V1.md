# X-Agent 已知问题与试点边界 v1

> 用途：把当前候选不能回避的已知缺口、试点限制与不支持范围显式写出来，避免交付时口头弱化。
>
> 适用范围：`candidate/min-send-review-20260707-claude` 当前代码线。

---

## 1. 当前一句话边界

当前 `xagent` 已达成商用交付标准，可按：

- **正式商用 GA**
- **受控私有部署**
- **单机 / Compose `full` 模式交付**
- **K8s / Helm 平台化部署（Roadmap v2 P0 已落地）**

来理解。

### 商用成熟度阶段映射

- G1（内部试点可稳定使用）：**已完成**
- G2（正式商用 GA）：**已完成**
- G3（企业级长期运营治理与首轮验证）：**已完成**
- 当前阶段：**Roadmap v2 增强期**（平台化 / 自动化运营 / 容量实证 / 商业复制 / 产品增强）

### 当前推进规则

- G1 / G2 / G3 均已关闭，不再回退到“是否达标”的旧问题
- 后续新增工作统一按 Roadmap v2 方向归类
- 新增强项不得回退已有 G0/G1/G2/G3 的完成结论

当前**不能**按以下口径对外承诺：

- 多实例 HA 已经过正式验证；
- 完整容量压测结论已签字；
- 所有 enterprise 接入点都已做客户现场验证。

---

## 2. 当前已知问题

## 2.1 目标环境 / full-mode 演练已完成

截至当前候选，R4 目标环境 / full-mode 演练已完成：

- isolated compose 项目 `xagent-r4` 已拉起，`/health` 与 `/ready` 返回 200；
- `alembic current` 为 `0005 (head)`；
- `python -m xagent.cli smoke` 通过；
- `tests/e2e/specs/full-flow.spec.ts --project=chromium` 已 9/9 通过。

该证据属于当前机器上的单机等价环境，不自动等同于客户目标环境签字。

## 2.2 正式 PR 审查包已闭环

当前候选已有 PR、已有远端 CI 绿色记录，R4 环境演练证据已完成。

## 2.3 运维体系已具备自动化基础

当前仓库已具备：

- `/health`、`/ready`、`/metrics`
- Langfuse 接入点
- Grafana dashboard 文件入口
- **PrometheusRule 告警规则 (6 条)**
- **Alertmanager 路由与通知配置**
- **自动恢复引擎 (LLM fallback / Worker 重启 / DB 连接池回收)**
- **证据自动归档 CronJob**
- **发布后观测自动汇总 (Helm post-upgrade hook)**

仍需后续推进：

- 正式容量压测基线报告 (P2)
- SLO 签字版
- 多实例 HA 演练

## 2.4 Helm / K8s 平台化已落地

Roadmap v2 P0 已完成：

- Helm Chart 产品化补齐 (_helpers.tpl, Namespace, SA, NetworkPolicy, PDB, ConfigMap)
- External Secrets Operator (ESO) 落地 (Vault/AWS/GCP/Azure)
- 多环境 values 模板 (dev/staging/prod/enterprise)
- 配置治理脚本 (validate_helm_values.py, render_env_diff.py)
- 配置治理收口 (2026-08-04)：门禁脚本单测 + CI `config-governance` 门禁 + 差异策略成文，详见 `docs/CONFIG_GOVERNANCE_V1.md`

仍需后续推进：

- 客户现场 K8s 集群级变更窗口治理
- 企业级多实例演练
- ~~lite 模式内存 UserStore 不跨实例共享~~（2026-08-04 P2 实测发现 → **2026-08-05 已修复**：UserStore DB 化——读透+写透 users 表，注册/改密/角色/删除跨重启与多实例生效，DB 不可用时降级内存不阻断登录；迁移 20260805_users_persist）

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

## 2.6 开发库 audit_events 历史断链（仅存量开发数据，生产无影响）

**现状**：长期使用的开发库（`apps/api/xagent.db`）`audit_events` 表存在历史断链——586 行中约 305 行为 GENESIS 类链起点（早期版本重启即重起链所致），另有约 97 行 `prev_hash` 指向不存在的哈希。这是开发过程遗留，**不影响新部署**。

**运行时隔离机制（代码已内建，见 `enterprise/chain.py`）**：

- 启动恢复时校验链完整性，校验失败记 `audit_chain_broken_on_restore` 错误日志；
- 断链旧行保留在库中供取证，不删除、不续写；
- 新链从 GENESIS 重起，且 `seq_floor` 越过存量最大 seq，新旧链不会混淆；
- 校验状态可通过 `/api/v1/audit/*` 端点查询。

**生产部署建议**：生产一律使用全新数据库初始化（`alembic upgrade head`），不携带开发库数据。若确需复用存量库，建议先通过 `scripts/backup.py`（`backup_audit`，经 `/api/v1/audit/export` 导出 JSON）归档审计历史，再清空 `audit_events` 表让链从干净的 GENESIS 开始：

```sql
-- 归档导出后执行（仅存量库复用场景）
DELETE FROM audit_events;
```

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

- 正式商用 GA 可交付
- 内部试点可交付
- 受控私有部署可交付
- K8s / Helm 平台化部署可交付
- 发布前审查准备已完成

### 当前不能成立

- 多实例 HA 已经过正式验证
- 完整容量压测结论已签字
- 所有环境演练完成（客户现场）
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

这份文档的目的不是放大风险，而是防止交付时把“可交付”说成“所有场景已验证”。

> **当前候选已达到商用交付标准，G1/G2/G3 已全部完成。Roadmap v2 P0(平台化)+P1(自动化运营) 已代码落地。后续 P2(容量实证)/P3(商业复制)/P4(产品增强) 按商业节奏推进。**
