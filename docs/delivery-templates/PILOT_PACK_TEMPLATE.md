# 标准试点包模板（P3 商业复制）

> 用途：把一次新试点交付收敛为可复用结构。复制本模板，替换 `<...>` 占位。
> 依据：G1-A1~A4 既有试点包（见 DELIVERY_MATERIALS_INDEX_V1）。

## 1. 试点定义

| 项 | 内容 |
|---|---|
| 客户/团队 | `<名称>` |
| 试点目标 | `<要在 N 周内证明的业务假设>` |
| 交付形态 | 单机 Docker Compose `full`（默认）/ Helm 单集群 |
| 候选版本 | `<commit/tag + CI run id>` |
| 周期 | `<起止日期>` |
| owner | `<姓名/角色>` |

## 2. 进入条件（Gate）

- [ ] 候选 CI 全绿（backend/frontend/license-gate/e2e-api）
- [ ] 目标环境按 R16 清单就绪（secret 用 secretRef 注入，无 lite 默认账号）
- [ ] LLM 路径已选通（Ollama / LiteLLM Proxy / 直连 provider 三选一）
- [ ] 试点边界页已与客户确认（KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1 的适用子集）

## 3. 标准使用路径（验收用）

1. 登录 → 修改默认口令（admin must_change_password）
2. 发起一个真实任务 → Run Console 观察流式执行
3. 技能库查看（自动提炼证据）
4. 一次受控失败 → 按 OPERATIONS_MANUAL 定位与恢复

## 4. 验收标准

| 指标 | 阈值 |
|---|---|
| 核心链路成功率 | `<如 ≥95%>` |
| P95 响应（非 LLM 端点） | `<如 <2s，参考 LOAD_TEST_FORMAL 基线>` |
| 无 P0/P1 事故 | 必需 |

## 5. 退出与转化

- [ ] 证据归档（runs、告警记录、运维日志）
- [ ] 试点回顾纪要
- [ ] 转正式（走 G2-B 系列包）或终止（环境清理清单）
