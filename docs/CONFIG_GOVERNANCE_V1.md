# 平台级配置治理与差异控制 v1

> Roadmap v2 · P0（平台化增强）收口文档 — 2026-08-04
>
> 本文定义 X-Agent Helm 多环境配置的治理模型、分级校验口径与环境差异策略，
> 并说明对应的机器校验入口（脚本 + 单测 + CI 门禁）。

---

## 1. 环境分层模型

配置采用 **base + overlay** 两层模型：

```text
deploy/helm/values.yaml                          # base：全环境共享默认值
deploy/helm/environments/values-dev.yaml         # overlay：仅声明与 base 的差异
deploy/helm/environments/values-staging.yaml
deploy/helm/environments/values-prod.yaml
deploy/helm/environments/values-enterprise.yaml
```

合并语义：深合并（dict 递归合并，标量/列表 overlay 覆盖 base），与
`helm -f values.yaml -f environments/values-<env>.yaml` 行为一致。
`scripts/validate_helm_values.py` 与 `scripts/render_env_diff.py` 内部使用
相同的合并逻辑，校验对象即"生效值"而非 overlay 文本。

原则：

- overlay 只写差异，不复制 base 内容；
- 任何真实 secret 一律不进 values 文件（生产走 ESO 或 `existingSecretRef`，
  见 `docs/ENVIRONMENT_BASELINE_V1.md` 第 8 章）。

---

## 2. 分级校验口径（validate_helm_values.py）

```bash
python scripts/validate_helm_values.py --env <dev|staging|prod|enterprise>
```

按环境分级强制（CRITICAL = 门禁失败，WARNING = 仅提醒）：

| 规则 | dev | staging | prod / enterprise |
|---|---|---|---|
| 必须启用 ESO（`secrets.eso.enabled`）或提供 `existingJwtSecretRef` | – | WARNING | CRITICAL |
| 禁止明文 `security.jwtSecret` | – | WARNING（弱默认值时） | CRITICAL |
| 禁止 `config.debug=true` | – | – | CRITICAL |
| 必须 `networkPolicy.enabled=true` | – | – | CRITICAL |
| 必须 `pdb.enabled=true` | – | – | CRITICAL |
| 必须 `alerting.enabled=true` | – | WARNING | CRITICAL |
| 禁止通配 CORS（`*`） | – | – | CRITICAL |
| 禁止关闭认证（`security.requireAuth=false`） | – | – | CRITICAL |
| 建议 `replicaCount >= 3` | – | – | WARNING |

退出码：存在 CRITICAL 时为 1，否则为 0（可直接做 CI 门禁）。

---

## 3. 环境差异策略（差异控制）

差异控制回答两个问题：**哪些键在环境间必须不同**（防止把 dev 配置带进生产），
**哪些键必须一致**（平台统一基线，防止漂移）。策略已固化为
`apps/api/tests/test_config_governance.py` 中的机器校验，与本文清单一一对应。

### 3.1 REQUIRED_DIFF_KEYS — dev 与 prod/enterprise 必须全部不同

| 键 | 理由 |
|---|---|
| `config.debug` | 生产禁止 debug |
| `config.corsOrigins` | 各环境前端域名必须显式区分 |
| `secrets.eso.enabled` | 生产强制 ESO，dev 关闭 |
| `networkPolicy.enabled` | 生产强制网络隔离 |
| `pdb.enabled` | 生产强制可用性保障 |
| `alerting.enabled` | 生产强制告警 |
| `replicaCount` | 容量分级（dev=1 / prod=3 / enterprise=5） |

另要求：任意两个环境在以上键上不得全同（防止 overlay 退化为 base 的复制）。

### 3.2 REQUIRED_SAME_KEYS — 四环境必须一致

| 键 | 理由 |
|---|---|
| `security.requireAuth` | 认证是全环境统一基线，任何环境不得关闭 |
| `serviceAccount.automountServiceAccountToken` | 统一最小权限基线 |

### 3.3 临时差异排查工具

```bash
python scripts/render_env_diff.py --from dev --to prod            # markdown 表格
python scripts/render_env_diff.py --from staging --to prod --format json
```

输出为 base+overlay 合并后的全量生效值 diff，用于评审"这次改动到底改变了哪些
环境的哪些键"。

---

## 4. 日常工作流

1. 修改 `deploy/helm/values.yaml` 或某环境 overlay；
2. 本地跑门禁三件套：

   ```bash
   for env in dev staging prod enterprise; do
     python scripts/validate_helm_values.py --env "$env"
   done
   helm template xagent ./deploy/helm -f deploy/helm/environments/values-<env>.yaml
   python scripts/render_env_diff.py --from dev --to <env>
   ```

3. 评审关注点：diff 中是否出现 §3.1 之外的意外差异、§3.2 基线键是否被动到；
4. CI `config-governance` job 兜底（四环境校验 + 五套渲染 + diff smoke）。

---

## 5. 机器校验入口汇总

| 层 | 入口 | 拦截内容 |
|---|---|---|
| 单测 | `apps/api/tests/test_config_governance.py` | 脚本回归 + 篡改用例 + §3 差异策略 |
| CI | `.github/workflows/ci.yml` job `config-governance` | 四环境 validate + helm template 五套渲染 + diff smoke |
| 本地 | `scripts/validate_helm_values.py` / `scripts/render_env_diff.py` | 提交前自检 |

## 6. 边界说明

- 本治理覆盖 **Helm values 层**；应用运行时 `SECRETREF:file:/env:` 语法治理见
  `docs/ENVIRONMENT_BASELINE_V1.md`；
- 客户现场 K8s 集群级变更窗口治理、企业级多实例演练仍为后续项
  （见 `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md` §2.4）。
