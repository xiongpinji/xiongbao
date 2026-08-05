# 企业内部助手变体包 v1

> 依据 `../../INDUSTRY_VARIANT_GUIDE.md` 裁剪矩阵建立的第二个行业/场景变体。
> 定位：把 X-Agent 作为**企业内部 AI 助手**（SSO 统一登录 + 知识库问答 + 强审计）
> 交付给企业职能/全员场景的变体口径与演示材料。主线代码零改动，纯口径与材料层。

## 1. 变体定义

| 项 | 内容 |
|---|---|
| 场景 | 企业员工统一入口的 AI 助手：企业 IdP 登录、内部知识库问答、全量审计留痕 |
| 差异要点 | SSO/OIDC 必配、审计保留加长、知识库预置（指南 §3 定义） |
| 主线能力锚点 | OIDC 三端点（`/oidc/providers` `/oidc/login` `/oidc/callback`，full 模式 Keycloak）、知识库 API（`POST /knowledge/ingest` `/knowledge/search` 等）、审计持久化（`PostgresAuditLog`）、证据归档保留期（`--retention-days`，enterprise overlay 已 365 天） |
| 交付形态 | **仅 full/enterprise 模式**（lite 内存 UserStore 不跨实例，见 KNOWN_ISSUES §2.4） |

## 2. 裁剪决策表（对照指南 §2 矩阵）

| 维度 | 本变体决策 |
|---|---|
| LLM 路径 | 可配 provider/代理拓扑；内网部署走 LiteLLM Proxy |
| 安全默认值 | **只加严**：SSO 必配（禁用本地口令登录演示）、token TTL 可按客户要求缩短；require_auth 等红线不动 |
| 技能库 | 预置职能向技能（文档问答/会议纪要/流程查询），不触技能质量门禁 |
| 工作流/模板 | 知识库预置包（员工手册/制度文档 ingest 脚本化），模板引擎不动 |
| 口径文案 | 见 `POSITIONING.md` |
| 合规 | **审计保留加长**：证据归档 retentionDays 按 enterprise overlay 365 天起步，可按客户合规要求再加长；审计事件覆盖范围不裁剪 |

## 3. 直接复用的主线模板（不复制）

试点包 / 升级包 / 恢复包 / 角色包直接引用 `docs/delivery-templates/` 原文。

## 4. 本变体独有材料

- [POSITIONING.md](POSITIONING.md) — 对外口径页（含 SOT 不可宣称项核对）
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md) — 客户演示脚本（SSO 登录 / 知识库问答 / 审计追溯）

## 5. 验收状态（对照指南 §4）

- [x] 主线路径回归不受影响（零代码改动，主线门禁即覆盖）
- [x] 变体特有项证据：演示脚本三条路径均基于主线已实现 API（见脚本内锚点）
- [x] 口径页已按 SOT §6.2 不可宣称项核对（见 POSITIONING §3）
