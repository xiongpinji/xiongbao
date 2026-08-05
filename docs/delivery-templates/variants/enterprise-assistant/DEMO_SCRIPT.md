# 企业内部助手变体 · 客户演示脚本

> 三条主路径，全部基于主线已实现能力。演示前置：full 模式环境已起
> （Keycloak 已配 realm，见 `deploy/keycloak/`），演示用 IdP 账号两个
> （普通员工 + 管理员），知识库已 ingest 若干客户制度文档。

## 路径 1：SSO 统一登录（企业采购第一关注点）

1. `GET /api/v1/auth/oidc/providers` → 展示 SSO 可用性（前端据此渲染 SSO 按钮）；
2. `GET /api/v1/auth/oidc/login` → 302 跳转企业 IdP 授权页；
3. 员工用 IdP 账号登录 → `/oidc/callback` 换票签发会话 → 进入工作台。

**预期结果**：全程无应用内账号注册/口令输入；登录后 `/api/v1/auth/me` 返回 IdP 身份。
**讲解点**：账号生命周期全部由企业 IdP 管控（离职即失效），应用侧不落账号库。

## 路径 2：知识库问答（全员价值演示）

1. 管理员现场上传一份制度文档：`POST /api/v1/knowledge/ingest`；
2. `GET /api/v1/knowledge/documents` 确认入库；
3. 员工提问：`POST /api/v1/knowledge/search` 语义检索命中该文档；
4. 在对话中引用检索结果完成问答。

**预期结果**：新上传文档可被即时检索命中。
**讲解点**：知识库管理员可维护（上传/列出/删除），无需厂商介入。

## 路径 3：审计追溯与证据归档（合规关注点）

1. 回放路径 1/2 的操作，展示审计事件（登录、检索、文档变更）已留痕；
2. 展示证据归档包结构（health-snapshot / recovery-logs / evidence-records，见
   `scripts/auto_archive_evidence.py` 产出）；
3. 说明保留期配置：enterprise 形态 retentionDays=365，可按合规要求加长。

**预期结果**：每个演示动作都有对应审计/证据记录可查。
**讲解点**：审计事件覆盖范围是平台统一红线，任何变体不得裁剪；保留期只能加长。

## 演示红线

- 不用 lite 模式演示（账号体系不符合企业口径）；不用本地口令账号演示；
- 知识库演示用客户授权的真实制度文档，不用编造内容；
- 演示环境 config 治理按 `docs/CONFIG_GOVERNANCE_V1.md` 跑门禁后再交付演示。
