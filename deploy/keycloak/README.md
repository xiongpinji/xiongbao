# Keycloak realm 导入与 SSO 部署说明

`xagent-realm.json` 是**开发/试点起点配置**（配合 `start-dev --import-realm` 使用），
交付部署前必须按实际环境调整。Keycloak 26 的 realm 导入 JSON **不支持环境变量
占位替换**，下列项需直接编辑文件或在管理控制台调整。

## 1. redirectUris / webOrigins 按部署调整（必做）

realm 文件中的 `xagent-api` client 预置了本地开发回退白名单：

```
http://localhost:3000/*   http://localhost:8000/*
http://127.0.0.1:3000/*   http://127.0.0.1:8000/*
```

- 生产部署时改为实际前端/API 来源，例如 `https://agent.example.com/*`，
  并删除不再使用的 localhost 条目（最小化白名单面）。
- `OIDC_REDIRECT_URI`（API 侧 env）必须落在该白名单内**精确匹配**
  （RFC-002：不用宽通配）。
- `webOrigins` 同步调整为实际来源（CORS 预检用）。

## 2. 导入后必做的三件事

realm JSON 不含 secret 与种子用户，导入后：

1. **取 client secret**：管理控制台 → Clients → `xagent-api` → Credentials，
   复制 Secret 填入 API 侧 `XAGENT_SECURITY__OIDC_CLIENT_SECRET`
   （或用 Admin API `GET /admin/realms/xagent/clients/{id}/client-secret`）。
2. **创建用户**：控制台或 Admin API 创建用户并设置密码。
3. **处理 KC26 首登 VERIFY_PROFILE 拦截**（见下节）。

## 3. KC26 新用户首登 VERIFY_PROFILE 拦截（交付侧处理方式）

Keycloak 26 默认启用 `VERIFY_PROFILE` required action：**通过 Admin API /
控制台创建的用户**（缺 firstName/lastName）首次登录会被拦截要求补全资料，
表现为 SSO 登录流程卡在资料补全页。交付时二选一：

- **关闭该 required action**（推荐给纯 API/系统集成场景）：
  管理控制台 → Authentication → Required actions → `Verify Profile` → 禁用；
  或 Admin API：
  ```bash
  curl -X PUT "$KC/admin/realms/xagent/required-actions/VERIFY_PROFILE" \
    -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
    -d '{"alias":"VERIFY_PROFILE","name":"Verify Profile","providerId":"VERIFY_PROFILE","enabled":false}'
  ```
- **管理员代验**：创建用户时直接补全 `firstName` / `lastName`（并建议
  `emailVerified: true`），用户首登即不会被拦截。

## 4. 快速启动（开发）

```bash
docker run -d --name xagent-keycloak -p 8180:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin123 \
  -v "$PWD/xagent-realm.json:/opt/keycloak/data/import/xagent-realm.json:ro" \
  quay.io/keycloak/keycloak:latest start-dev --import-realm
```

API 侧配套 env（值按实际部署替换）：

```bash
XAGENT_SECURITY__OIDC_CLIENT_ID=xagent-api
XAGENT_SECURITY__OIDC_CLIENT_SECRET=<导入后从控制台取>
XAGENT_SECURITY__OIDC_ISSUER=http://127.0.0.1:8180/realms/xagent
XAGENT_SECURITY__OIDC_JWKS_URL=http://127.0.0.1:8180/realms/xagent/protocol/openid-connect/certs
XAGENT_SECURITY__OIDC_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/oidc/callback
```

详细设计见 `docs/rfc/RFC-002-sso-oidc.md`。
