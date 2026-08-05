# 研发效能变体包 v1（Codex 对标场景）

> 依据 `../../INDUSTRY_VARIANT_GUIDE.md` 裁剪矩阵建立的首个行业/场景变体。
> 定位：把 X-Agent 作为**研发效能平台**（代码评审 + 分层指令 + 权限治理）交付给
> 研发团队客户的变体口径与演示材料。主线代码零改动，纯口径与材料层。

## 1. 变体定义

| 项 | 内容 |
|---|---|
| 场景 | 研发团队 AI 助手：代码评审、仓库级指令治理、企业权限管控 |
| 对标 | OpenAI Codex（分层指令语义对齐）、静态评审平台 |
| 主线能力锚点 | `code_review` 域（`POST/GET /api/v1/code-review`）、`xagent/core/instructions`（AGENTS.md 三层合并）、`require_permission` 权限点（`code_review:execute/read`） |
| 交付形态 | 与主线一致（Compose full / Helm），无独立构建 |

## 2. 裁剪决策表（对照指南 §2 矩阵）

| 维度 | 本变体决策 |
|---|---|
| LLM 路径 | 可配 provider/模型档位；评审场景建议降本档位 + fallback 链 |
| 安全默认值 | 沿用主线（不加严也不放松）；密钥注入走 secretRef，不变 |
| 技能库 | 预置研发向技能（代码评审/重构/测试生成），不触技能质量门禁 |
| 工作流/模板 | 复用主线评审 API，无行业模板新增 |
| 口径文案 | 见 `POSITIONING.md`（产品名/案例可行业化） |
| 合规 | 审计事件覆盖范围不动；保留期可按客户要求加长 |

## 3. 直接复用的主线模板（不复制）

试点包 / 升级包 / 恢复包 / 角色包直接引用 `docs/delivery-templates/` 原文，
本变体不另维护副本，避免双源漂移。

## 4. 本变体独有材料

- [POSITIONING.md](POSITIONING.md) — 对外口径页（含 SOT 不可宣称项核对）
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md) — 客户演示脚本（三条主路径 + 预期结果）

## 5. 验收状态（对照指南 §4）

- [x] 主线路径回归不受影响（零代码改动，主线门禁即覆盖）
- [x] 变体特有项证据：演示脚本三条路径均基于主线已实现 API（见脚本内锚点）
- [x] 口径页已按 SOT §6.2 不可宣称项核对（见 POSITIONING §3）
