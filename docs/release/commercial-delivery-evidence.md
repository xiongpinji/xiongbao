# X-Agent 商用交付证据边界

本文件规定商用候选证据的固定读取方式。机器事实源是当前 SHA 对应目录中的 `commercial-delivery-manifest.json`；本文件不替代机器清单，也不把历史构建、单元测试或 CI 组件结果提升为端到端验收。

## 候选身份

- 实际仓库：记录绝对工作树路径，不使用临时终端目录代称。
- 分支：必须与五个 `gate.json` 的 `branch` 一致。
- SHA：必须为当前 `git rev-parse HEAD` 的 40 位值。
- 工作树：五门开始和结束时均为 `dirty: false`，最终聚合再次检查 porcelain 为空。
- 分类：只有五门同 SHA 且制品哈希复算通过时才是 `candidate_local`。

## 五门证据

| 门 | 必须证明 | 不能推断 |
|---|---|---|
| commercial_kernel | 版本、Windows preflight、秘密不落盘、安全检查、锁定依赖审计、不可变镜像合同 | 不能推断业务端到端通过 |
| webapi | 完整 API、Web、SDK、六服务、迁移、真实本地模型、三轮零重试浏览器主链 | 不能推断外部供应商或客户环境通过 |
| short_drama | 本地离线成片、重开、下载、ZIP 独立哈希和 provider 边界 | 不能推断付费媒体供应商验收 |
| desktop | Rust 质量、MSI/NSIS、安装后二进制诊断、两次 GUI 生命周期、卸载、签名状态 | 未签名候选不能称为正式桌面发布 |
| rollback | 两租户数据、备份、空目标恢复、baseline→current→baseline、Qdrant、审计与 ZIP 连续 | 不能推断客户真实数据恢复完成 |

每个门必须保存非空 `commands`、退出码、通过/失败/跳过计数以及 `artifacts` 的相对路径、大小和 SHA-256。聚合器从文件重新计算摘要；摘要不一致即失败。

## 命令与制品摘要

最终报告从机器清单读取以下字段：

- `command_totals.passed`、`command_totals.failed`、`command_totals.skipped`；
- `artifact_count`；
- Web/API 的真实本地模型和 Playwright retry 数；
- 短剧的 `provider_classification` 与外部 provider 授权；
- 桌面端 MSI/NSIS SHA-256、大小和 Authenticode 状态；
- `backup-manifest.json`、`restore-manifest.json`、镜像 ID、三个运行阶段与数据计数。

跳过只允许分为显式的环境边界或未授权外部动作。任何核心本地命令退出非零、`failed > 0`、证据缺失或 SHA 漂移都不能归为跳过。

## 三层交付边界

### 1. 本地候选

`candidate_local` 只表示当前 Windows 工作站、当前仓库 SHA 和本轮隔离服务已经通过五门。它允许交付本地候选制品与审计清单，不授权推送、发布、部署、付费调用或客户数据写入。

### 2. 正式发布

正式发布还要求受信任代码签名和时间戳、远端 CI 的同 SHA 成功记录、受保护发布环境审批、制品仓库落库、发布说明和发布后复核。CI 的 `ci_component_evidence` 不是本地五门，也不能单独生成正式发布结论。

### 3. 客户生产

客户生产还要求客户目标环境的网络、身份、密钥托管、容量、监控、真实供应商、计费、备份恢复和业务验收。正式发布成功不能推断客户生产验收成功。

## 外部授权固定值

本地最终清单必须保持以下四项：

- `remote_release: not_authorized`
- `production_deployment: not_authorized`
- `paid_provider_acceptance: not_authorized`
- `customer_production_acceptance: not_authorized`

只有用户针对具体目标另行授权并完成对应外部验证后，才能在独立发布记录中改变这些状态；不得修改本地候选历史清单来追认。
