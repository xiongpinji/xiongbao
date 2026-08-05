# 研发效能变体 · 客户演示脚本

> 三条主路径，全部基于主线已实现能力。演示前置：Compose full 或 Helm dev 环境
> 已起（见 `docs/delivery-templates/PILOT_PACK_TEMPLATE.md` 进入条件），
> 演示账号具备 `code_review:execute/read` 权限。

## 路径 1：代码评审（核心锚点）

1. 取客户一个真实 PR 的 diff（`git diff base..head > demo.diff`）；
2. `POST /api/v1/code-review`，body 直传 diff（或 repo+base..head 形式）；
3. 现场展示返回的结构化评审结果；
4. `GET /api/v1/code-review/{review_id}` 回查同一结果，证明结果可留存、可追溯。

**预期结果**：返回评审结论与问题列表；两次查询结果一致。
**讲解点**：评审走 LLM 链路但入口是标准 API，可挂进 CI 或流水线。

## 路径 2：AGENTS.md 分层指令治理（Codex 对标点）

1. 现场在演示仓库根放一个 `AGENTS.md`（如"本仓库统一用中文 commit"）；
2. 在子目录再放一个就近 `AGENTS.md`（如"本目录为遗留代码，只做最小修改"）；
3. 触发一次涉及该子目录的任务，展示注入的指令同时包含三层来源标注，
   且子目录规则在冲突处覆盖根规则。

**预期结果**：模型行为遵守子目录级约束；注入内容可见来源层级。
**讲解点**：与 Codex 分层指令语义对齐；团队规范沉淀为仓库文件，随代码评审与版本管理。

## 路径 3：权限与审计（企业采购关注点）

1. 用无 `code_review:execute` 权限的账号调用路径 1 的 API → 403；
2. 换有权限账号 → 200；
3. 展示审计侧对应事件记录（审计事件覆盖范围为主线统一口径，不可裁剪）。

**预期结果**：权限拦截即时生效；审计事件可检索。
**讲解点**：资源:动作粒度权限点；full 模式对接 Keycloak SSO，账号不进应用库。

## 演示红线

- 不用造假的评审结果截图；不用 lite 默认 admin/admin 账号演示企业权限；
- 演示环境 config 治理按 `docs/CONFIG_GOVERNANCE_V1.md` 跑门禁后再交付演示。
