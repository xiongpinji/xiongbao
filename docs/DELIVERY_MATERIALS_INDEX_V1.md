# X-Agent 交付材料索引 v1

> 用途：把正式交付检查表第九节需要的材料收敛到一个可直接引用的入口。
>
> 适用范围：当前 `xagent` 单机 / Docker Compose `full` 模式交付、内部试点、受控私有部署。
>
> 边界：本索引只解决“材料是否成套、入口是否明确”，**不替代** `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 中的远端 CI、R4 目标环境演练、Reviewer 验收和 TL / QA / DevOps / Owner 签字。

---

## 1. 当前材料清单

| 材料 | 文档入口 | 当前状态 | 说明 |
|---|---|---|---|
| 管理员部署手册 | [ADMIN_DEPLOYMENT_MANUAL_V1.md](ADMIN_DEPLOYMENT_MANUAL_V1.md) | READY | 面向交付负责人 / 客户管理员，覆盖 single-node `full` 模式部署前置、发布步骤和交付归档要求 |
| 运维手册 | [OPERATIONS_MANUAL_V1.md](OPERATIONS_MANUAL_V1.md) | READY | 面向运维 / 发布值守，覆盖健康检查、日志、备份、恢复入口、例行巡检与异常分流 |
| 升级 / 回滚说明 | [RELEASE_RUNBOOK_V1.md](RELEASE_RUNBOOK_V1.md) | READY | 当前唯一发布 / 回滚执行手册 |
| 已知问题列表 | [KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md](KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md) | READY | 明确当前候选不能被表述为正式 GA 的已知缺口与限制 |
| 试点边界说明 | [KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md](KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md) | READY | 与已知问题合并维护，避免双份口径漂移 |
| 试点功能链路包 | [coordination/reports/commercialization-g1-a1-functional-package.md](coordination/reports/commercialization-g1-a1-functional-package.md) | READY | 固定内部试点标准日常使用路径、关键入口、现有证据与最小验证命令，作为 G1-A1 的交接入口 |
| 稳定性 / 恢复包 | [coordination/reports/commercialization-g1-a2-stability-package.md](coordination/reports/commercialization-g1-a2-stability-package.md) | READY | 冻结内部试点阶段的失败观察入口、恢复动作、最小演练脚本与现有证据链接，作为 G1-A2 的交接入口 |
| 数据 / 权限 / 审计包 | [coordination/reports/commercialization-g1-a3-data-governance-package.md](coordination/reports/commercialization-g1-a3-data-governance-package.md) | READY | 冻结内部试点阶段的权限边界、运行对象回查关系、最小审计入口与 secret / 默认值约束，作为 G1-A3 的交接入口 |
| 试点交付材料包 | [coordination/reports/commercialization-g1-a4-pilot-delivery-package.md](coordination/reports/commercialization-g1-a4-pilot-delivery-package.md) | READY | 收敛内部试点阶段的部署、运维、边界、升级路径与 G1-A1/A2/A3 入口，作为 G1-A4 的最终交接入口 |
| G1 稳定性演练记录 | [coordination/reports/commercialization-g1-stability-rehearsal.md](coordination/reports/commercialization-g1-stability-rehearsal.md) | READY | 为 G1 Gate 2 提供一条失败→定位→恢复的最小演练记录，证明内部试点阶段已具备稳定性闭环证据 |
| G2 候选冻结包 | [coordination/reports/commercialization-g2-b1-candidate-freeze-package.md](coordination/reports/commercialization-g2-b1-candidate-freeze-package.md) | READY | 冻结正式商用 GA 的唯一候选对象、范围、CI 与证据入口，作为 G2-B1 的执行入口 |
| 目标环境演练包 | [coordination/reports/commercialization-g2-b2-target-rehearsal-package.md](coordination/reports/commercialization-g2-b2-target-rehearsal-package.md) | READY | 冻结正式商用 GA 候选在目标环境 / full-mode 下的演练步骤、证据要求、发布 / 回滚 / smoke 闭环，作为 G2-B2 的执行入口 |
| 发布 / 回滚包 | [coordination/reports/commercialization-g2-b3-release-rollback-package.md](coordination/reports/commercialization-g2-b3-release-rollback-package.md) | READY | 冻结正式商用 GA 候选的发布步骤、回滚边界、失败处置与 smoke 闭环，作为 G2-B3 的执行入口 |
| 签字 / 证据包 | [coordination/reports/commercialization-g2-b4-signoff-evidence-package.md](coordination/reports/commercialization-g2-b4-signoff-evidence-package.md) | READY | 冻结正式商用 GA 的 reviewer / owner 签字入口、证据索引与最终结论模板，作为 G2-B4 的执行入口 |
| 联系人与故障升级路径 | [SUPPORT_ESCALATION_PATH_V1.md](SUPPORT_ESCALATION_PATH_V1.md) | READY | 当前单人交付模式下已明确由 owner `canqu` 同时承担 L1/L2/L3/L4；若后续转入外部团队或客户现场，再补企业联系方式与 SLA |

---

## 2. 当前应如何使用

### 2.1 内部试点 / 受控交付

当前可直接使用：

1. [ADMIN_DEPLOYMENT_MANUAL_V1.md](ADMIN_DEPLOYMENT_MANUAL_V1.md)
2. [OPERATIONS_MANUAL_V1.md](OPERATIONS_MANUAL_V1.md)
3. [RELEASE_RUNBOOK_V1.md](RELEASE_RUNBOOK_V1.md)
4. [KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md](KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md)
5. [SUPPORT_ESCALATION_PATH_V1.md](SUPPORT_ESCALATION_PATH_V1.md)（先按角色使用，再补真实联系人）

### 2.2 正式商用签发前

除材料成套外，还必须额外完成：

- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` 第二节所有 P0 阻断项；
- 当前候选对应的远端 CI 全绿记录；
- `R4` 目标环境 / full-mode 演练证据归档；
- `R5` PR 审查包签发；
- TL / QA / DevOps / Owner 共同签字；
- [SUPPORT_ESCALATION_PATH_V1.md](SUPPORT_ESCALATION_PATH_V1.md) 中真实联系人补齐。

---

## 3. 与其他核心文档的关系

- 当前真实状态：[`COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`](COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md)
- 发布门禁：[`COMMERCIAL_RELEASE_CHECKLIST_V1.md`](COMMERCIAL_RELEASE_CHECKLIST_V1.md)
- 发布 / 回滚执行：[`RELEASE_RUNBOOK_V1.md`](RELEASE_RUNBOOK_V1.md)
- 环境基线 / secret：[`ENVIRONMENT_BASELINE_V1.md`](ENVIRONMENT_BASELINE_V1.md)
- Compose 部署细节：[`DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md)

---

## 4. 当前结论

截至当前候选，这套交付材料已经足以支撑：

- **内部试点 / 受控交付的材料成套性**；
- **发布前 reviewer 能找到部署、运维、已知问题、试点边界和升级路径入口**。

但它**还不足以单独证明正式商用可交付**；正式结论仍取决于 R4、R5、远端 CI 和最终签字。
