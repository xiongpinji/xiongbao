# R17 证据矩阵刷新附录（2026-08-03）

> 性质：R17（PR 证据矩阵源数据，已验收 DONE）的**刷新附录**，不回写历史包。
> 触发：验收材料包（REVIEW_ACCEPTANCE_PACKET_20260803）登记的后续小包。
> 边界：与 R17 相同——源数据，不是最终 PR 文案，不签发检查表，不替代 R4/R5 gate。

## 刷新项

### §2.4 安全默认值（原：Baseline covered, target secrets pending）→ 增强

| 新证据 | 来源 |
|---|---|
| 全模式默认 require_auth=true；admin 默认口令 must_change_password（实测） | DELIVERY_VERIFICATION_20260803 v3 §三 |
| shell_exec/python_exec 默认禁用，注册+运行时双层门禁；python_exec 在沙箱 disabled 时 fail-closed（8bfb826） | 同上；docs/deployment/sandbox.md |
| SSO/OIDC 授权码流端到端实测（Keycloak 26：discovery/换票/JWKS 验签/JIT 开户/state 防重放/双源 token 共存） | SANDBOX_SSO_REVERIFY_20260803 |
| token 校验按 alg 路由双源（HS256 本地 / RS256 JWKS），伪造双算法均拒 | 0865e19 + 7 项测试 |
| secretRef 外部密管（file:/env:，生产 fail-fast，vault 预留） | 944675b；R16 §8 增补 |

### §2.6 CI 与质量门禁（原：strong local/remote evidence, with caveats）→ 增强

| 新证据 | 来源 |
|---|---|
| PR #7 新候选 CI 全绿：backend/frontend/license-gate/**e2e-api**（run 30829673045 + cfb973d 最新 run） | gh pr view 7 |
| e2e-api 与 backend 解耦（`if: always() && != cancelled`），防止 backend 红连带 SKIPPED 掩盖 API 口径漂移 | 本轮 ci.yml 修改 |
| /perf 端点存量 bug 修复（TimingMiddleware 实装） | 402302a |
| 后端全量 pytest 多轮 exit 0（含 bcrypt/skills/perf 修复后回归） | audit-20260802/pytest_verify_*.log |

### §8 性能与容量（原：Mostly open）→ 已有正式证据

| 证据 | 结论 |
|---|---|
| 10min soak（c=10 混合端点） | 142,720 请求全 200，吞吐 220~242 RPS 无衰减，无内存泄漏迹象（RSS 阶跃归因调度任务） |
| Postgres 目标配置基线 | 各端点不劣于 SQLite；login c=50 66.4 RPS |
| 多 worker（4）形态 | canvas c=10 606 RPS（6.4×），login c=50 86.5 RPS |
| 三瓶颈修复实测 | bcrypt 线程池化（login 17×）、skills 响应缓存（5.2×）、限流配置化 |

证据入口：`audit-20260802/LOAD_TEST_FORMAL_20260803.md`、`LOAD_TEST_BASELINE_20260803.md`。

### §1 版本与范围（补充）

- 新候选 HEAD `cfb973d`（R5 包 v2 附录），原签字候选 `c175201` 后推进 221 提交，owner 重新签发为剩余 gate。

## 未变更项（保持 R17 原口径）

- §2.5 R4 目标环境演练：当前机器等价演练（R31）已 DONE；**非当前机器的目标环境演练仍是发布 owner 决策项**。
- §7 数据与恢复：目标 DB 备份/恢复演练仍未做。
- §10：仍不是正式 GA 签字。
