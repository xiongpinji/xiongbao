# RFC-002：SSO/OIDC 接通 Keycloak（授权码回调落地）

- **状态**：Draft（提案，未实施）
- **作者**：工作流 F（竞品差距推进）
- **日期**：2026-08-02
- **关联**：`xagent/enterprise/auth/jwt_auth.py`（OIDC 验签已有）、`SecuritySettings`（`keycloak_url / keycloak_realm / oidc_jwks_url / oidc_issuer`）、README 架构表「enterprise: Keycloak + Casbin/OpenFGA/OPA」

## 1. 背景与现状

X-Agent 企业叙事里 SSO 底座是 Keycloak，当前**已完成的一半**：

- Bearer token 的 OIDC 验签链路已通：配置 `XAGENT_SECURITY__OIDC_JWKS_URL` 后，`decode_token` 优先走 JWKS/RS256 验签，claims 映射（`sub→user_id`、`realm_access.roles→roles`、`tenant_id`）已实现。

**缺的一半**：没有浏览器登录链路。用户无法通过 Keycloak 登录页完成认证——没有 `/auth/oidc/login` 跳转、没有 `/auth/oidc/callback` 回调、没有 state/nonce 防重放、没有会话建立。full/enterprise 客户只能手工从 Keycloak 换 token 再调 API，不可交付。

## 2. 目标与非目标

**目标**：打通 OIDC Authorization Code Flow（浏览器 → Keycloak 登录 → 回调 → 建立 X-Agent 会话），让私有化部署客户用自己已有的 Keycloak 完成 SSO。

**非目标**：

- 不做 SAML / LDAP（Keycloak 侧可自行联邦）；
- 不做 IdP 发起的 SSO / SLO 单点登出（列入后续）；
- 不替换 lite 内置 JWT 登录（admin/admin 本地账号保持，OIDC 是 full/enterprise 增量）。

## 3. 方案

### 3.1 端点设计（挂在 enterprise/auth 下，复用现有薄路由风格）

| 端点 | 方法 | 行为 |
|---|---|---|
| `/api/v1/auth/oidc/login` | GET | 生成 `state`+`nonce`（签名/存 cache，TTL 10min），302 跳转到 Keycloak `authorization_endpoint`（`response_type=code&scope=openid profile email`） |
| `/api/v1/auth/oidc/callback` | GET | 校验 `state`，用 `code` 调 `token_endpoint` 换 `id_token`+`access_token`，JWKS 验签 + `nonce` 比对，映射 Principal，签发 X-Agent 会话（HttpOnly Cookie 或回跳前端携带 access_token） |

### 3.2 配置（复用现有 `SecuritySettings`，仅补两个字段）

```
XAGENT_SECURITY__KEYCLOAK_URL=https://sso.corp.example
XAGENT_SECURITY__KEYCLOAK_REALM=xagent
XAGENT_SECURITY__OIDC_JWKS_URL=https://sso.corp.example/realms/xagent/protocol/openid-connect/certs
XAGENT_SECURITY__OIDC_ISSUER=https://sso.corp.example/realms/xagent
XAGENT_SECURITY__OIDC_CLIENT_ID=xagent-web        # 新增
XAGENT_SECURITY__OIDC_CLIENT_SECRET=***            # 新增（confidential client）
```

新增字段 `oidc_client_id / oidc_client_secret`，缺省时 OIDC 登录端点返回 503「未配置 SSO」，不影响现有 Bearer 验签。

### 3.3 用户与租户落地

- 首次回调成功时按 `sub`（或 `preferred_username`）在 `enterprise/auth/users.py` 自动开户（JIT provisioning），角色取 Keycloak `realm_access.roles` 与本地角色的交集映射，默认 `member`；
- `tenant_id` 取自定义 claim `tenant_id`（Keycloak mapper 配置写入部署手册），缺省 `default`；
- 审计：登录成功/失败写 `enterprise/audit`（event=`sso_login`），与现有多租户审计黑板一致。

### 3.4 前端

- 设置页/登录页在 `GET /api/v1/system/capabilities`（或等价端点）报告 `sso_enabled=true` 时显示「企业 SSO 登录」按钮，跳转 `/api/v1/auth/oidc/login`；
- 回调完成后 302 回前端 `/runs`（token 走 HttpOnly Cookie 时无感；走 query 携带时前端落 localStorage 后清 URL——优先 Cookie 方案避免 token 落历史记录）。

## 4. 实施步骤（建议顺序）

1. `SecuritySettings` 增加 `oidc_client_id / oidc_client_secret`；capability 上报 `sso_enabled`；
2. `enterprise/auth/` 新增 `oidc_flow.py`：discovery（`.well-known/openid-configuration` 带缓存）+ login 跳转 + callback 换票 + state/nonce 防重放（复用 `adapters/cache`）；
3. 路由：`/api/v1/auth/oidc/login|callback`（薄路由，逻辑全在 service 层）；
4. JIT 开户 + 角色映射 + 审计事件；
5. 会话策略：HttpOnly Cookie（`SameSite=Lax`，生产 `Secure`）优先，保留 Bearer 双轨；
6. 前端登录页 SSO 按钮 + 回调落地页；
7. 部署手册：Keycloak realm/client 创建、redirect_uri 白名单、tenant_id claim mapper 配置；
8. 测试：
   - 单测：mock token_endpoint/JWKS，验证 state 不匹配拒绝、nonce 重放拒绝、claims→Principal 映射；
   - 集成：docker-compose 起 Keycloak（deploy/compose 已有依赖服务编排惯例），脚本化走通 login→callback→带 Cookie 访问受保护端点；
   - 回归：内置 JWT 登录（admin/admin）不受影响。

## 5. 安全要点

- `state` 一次性、TTL 10 分钟、与回调 IP/UA 弱绑定可选；
- `nonce` 必须回比 `id_token`；
- `id_token` 验签强制 RS256 + `iss`/`aud`/`exp` 全校验（复用 `_decode_oidc` 的严格项）；
- `client_secret` 只走环境变量/secret 管理，不进 `.env.example` 真值；
- 回调 URL 路径固定，redirect_uri 必须在 Keycloak client 白名单内精确匹配（不用通配）。

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 客户 Keycloak 版本差异（claims 结构不同） | claims 映射做成可配置（claim 名环境变量），手册给 18/24/26 三版实测配置 |
| 内网部署 API 无法直连 IdP token_endpoint | 支持 `OIDC_JWKS_URL` 独立配置 + 部署手册标注网络要求 |
| 会话固定/CSRF | state + SameSite=Lax + 回调一次性 |
| 与 lite 模式混淆 | OIDC 端点仅在配置了 client_id 时启用；lite 默认不暴露 |

## 7. 度量

- SSO 登录成功率 ≥ 99%（审计事件统计）；
- 回调 P95 延迟 < 1.5s（排除 IdP 网络）；
- 部署手册实测：新客户 Keycloak 接通时间 < 0.5 人日。
