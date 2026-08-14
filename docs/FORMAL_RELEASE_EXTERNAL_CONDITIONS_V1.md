# X-Agent 正式交付剩余外部条件与 R4 环境输入清单 v1

> 用途：给发布负责人、环境负责人、QA/Reviewer 和 Owner 一页讲清楚——**当前正式交付还差什么，而且这些差项已经不再是代码问题，而是外部环境 / 证据 / 签字问题。**
>
> 适用范围：当前候选分支 `candidate/min-send-review-20260707-claude`。
>
> 边界：本文档不替代 `docs/RELEASE_RUNBOOK_V1.md` 的执行步骤，也不把 R4 演练、R5 审查包或最终签字写成已完成。

---

## 1. 当前已完成到什么程度

截至当前候选，可直接确认：

- 当前候选分支：`candidate/min-send-review-20260707-claude`
- 当前 PR：`#7` `chore(readiness): freeze minimal send-review candidate`
- 当前远端 CI：GitHub Actions `CI` run `28914695375` 成功
- 当前 PR 检查项已绿：`backend` / `frontend` / `license-gate` / `promptfoo-eval`
- 本轮仓库内可直接补齐的交付材料已形成：
  - [DELIVERY_MATERIALS_INDEX_V1.md](DELIVERY_MATERIALS_INDEX_V1.md)
  - [ADMIN_DEPLOYMENT_MANUAL_V1.md](ADMIN_DEPLOYMENT_MANUAL_V1.md)
  - [OPERATIONS_MANUAL_V1.md](OPERATIONS_MANUAL_V1.md)
  - [KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md](KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md)
  - [SUPPORT_ESCALATION_PATH_V1.md](SUPPORT_ESCALATION_PATH_V1.md)

结论：

> **当前剩余阻断项已经不应再通过“继续改功能代码”来解决；剩余问题主要是 R4 环境演练、R5 签发级证据、真实联系人与最终签字。**

---

## 1.5 2026-08-14 状态刷新（v1.1.1 后）

- 候选/master/tag 三段 CI 与双 Release（v1.1.0、v1.1.1）已完成，本机等价环境全栈演练已完成（见 `RELEASE_SIGNOFF_PACKAGE_V1.1.1.md`）。
- 剩余外部条件均已"一键可执行化"：
  - 发布签字 → `docs/RELEASE_SIGNOFF_PACKAGE_V1.1.1.md` 第 6 节签字矩阵
  - 多机 HA 演练 → `scripts/ha_drill.py`（已在本机双实例实测 PASS；共享 Redis 部署加 `--expect-shared-lock`）
  - E2B L2 实测 → `scripts/verify_e2b_sandbox.py`（取得 E2B_API_KEY 后一条命令完成）

---

## 2. 当前只剩哪些外部条件

| 阻断项 | 当前状态 | 需要谁提供 | 完成定义 |
|---|---|---|---|
| R4 目标环境 / full-mode 演练 | 未完成 | 环境负责人 + 发布负责人 | 在目标环境或 staging 等价环境实际跑通，并归档日志 / smoke / E2E / 回滚信息 |
| R5 PR 审查包签发 | 待 R4 证据后推进 | Reviewer / 发布负责人 / Owner | PR 包含环境演练证据、风险摘要、验证矩阵、reviewer 关注点并可正式送审 |
| 真实支持联系人 | 当前单人交付模式下已明确 | — | 当前 owner `canqu` 在本轮交付中同时承担 L1/L2/L3/L4；若转入客户现场或外部团队，再补企业联系方式 |
| 最终签字 | 未完成 | TL / QA / DevOps / Owner | 对应签字角色确认本次环境、候选和证据满足正式交付门禁 |

---

## 3. R4 必须补齐的环境输入

## 3.1 候选绑定信息

发布负责人必须明确：

- Release ID / 版本号
- 候选分支：`candidate/min-send-review-20260707-claude`
- 候选 commit SHA
- PR URL：PR #7
- CI run URL / run id：`28914695375`
- 发布环境名称：staging / rehearsal / prod
- 发布负责人
- 回滚负责人
- 变更窗口

没有这些信息时，不要开始 R4。

## 3.2 必填 secret / 配置来源

环境负责人至少提供以下内容的**真实来源**（可以是 secret manager 路径、CI secret 名、平台注入项；不要把真实 secret 写入 Git）：

- `XAGENT_SECURITY__JWT_SECRET`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_SALT`
- `LANGFUSE_INIT_USER_PASSWORD`
- `XAGENT_CORS_ORIGINS`
- `POSTGRES_PASSWORD`（若使用 compose 内置 Postgres）
- 若启用 LiteLLM：`XAGENT_LLM__PROXY_URL` / `XAGENT_LLM__PROXY_API_KEY`
- 若直连 provider：OpenAI / DeepSeek key 来源

## 3.3 full-mode 显式账号

必须提供：

- full-mode 登录账号来源
- 用户名 / 邮箱标识
- 密码来源或初始化方式
- 是否需要 tenant_id

明确限制：

- 不允许把 `admin/admin` 当作 full-mode 验收账号；
- lite/dev 的默认登录结果不能替代 R4 现场证据。

## 3.4 LLM 路径

必须明确至少一条可用路径：

- 宿主机 Ollama
- LiteLLM proxy
- OpenAI / DeepSeek provider

并补齐：

- 目标模型名
- 可达地址
- 鉴权方式
- 若是 Ollama，宿主机是否已拉好模型

## 3.5 依赖服务与端口

需要环境负责人确认：

- `5432` Postgres
- `6379` Redis
- `6333/6334` Qdrant
- `3001` Langfuse
- `4000` LiteLLM
- `8000` API
- `3000` Web
- `8080` ContextForge
- `8081` OpenFGA

至少要能回答：

- 哪些由 compose 拉起
- 哪些由平台侧预置
- 当前是否有端口冲突
- 是否允许执行 `docker compose up -d --build`

---

## 4. R4 完成时必须回传的证据

环境侧完成 R4 后，至少回传：

- `docker compose --env-file .env config --quiet` 结果
- `docker compose ps`
- Alembic current / upgrade / current 输出
- `/health` 结果
- `/ready` 结果
- 前端入口结果
- full-mode 登录结果
- 至少一组 smoke / E2E 结果
- `api` / `worker` / `web` 日志路径或摘录
- 若发生回滚：回滚开始时间、结束时间、回滚版本、恢复结果

统一归档入口：

- [RELEASE_RUNBOOK_V1.md](RELEASE_RUNBOOK_V1.md)
- [delivery-report.md](coordination/reports/delivery-report.md)

---

## 5. 哪些东西不能再拿来充当正式交付证据

以下内容**不能**再被拿来冒充正式交付闭环：

- lite/dev 下的 `admin/admin` 登录结果
- 仅本地工作站上的 `/health` / `/ready` 截图
- 只证明代码存在的 E2E spec 文件
- 没有目标环境实跑的 `.env.example`
- 没有实名联系人的角色占位表
- 没有 TL / QA / DevOps / Owner 的口头通过

---

## 6. 现在给环境负责人的最小交付请求

由于当前是单人交付模式，这里的“环境 / 发布负责人”默认就是 owner 本人。对本轮当前机器的 R4 演练，这一节已经实跑完成；只有在后续切换到其他机器、客户现场或外部环境时，才需要按下面清单再次补齐输入。

可以直接把下面这段发给后续环境 / 发布负责人：

```text
当前 candidate/min-send-review-20260707-claude 的仓库内代码、CI 和最小交付材料已收口，正式交付剩余阻断主要是 R4 目标环境/full-mode 演练与最终签字。

请提供：
1) 本次演练环境名、发布负责人、回滚负责人、变更窗口；
2) JWT/Langfuse/CORS/Postgres 等必填配置的真实来源（secret manager path / CI secret name / 平台注入项）；
3) full-mode 显式登录账号来源；
4) 至少一条可用 LLM 路径（Ollama / LiteLLM / provider）；
5) 依赖服务与端口准备状态；
6) 允许执行 compose config / up / migration / smoke / E2E 的窗口。

环境条件一旦补齐，就按 docs/RELEASE_RUNBOOK_V1.md 执行，并把日志、health/ready、登录、Run Console、smoke/E2E、回滚信息归档到 docs/coordination/reports/delivery-report.md。
```

---

## 7. Claude 接下来还能直接做什么

一旦上面的外部条件补齐，Claude 还可以继续负责：

- 复核环境输入是否完整；
- 帮你逐条执行 runbook；
- 记录 R4 演练证据；
- 整理 R5 reviewer 输入；
- 核对哪些项已经足以进入最终签字。

---

## 8. 当前结论

> **当前正式交付的剩余阻断，已经不是“代码没做完”，而是“环境没实跑、证据没回传、联系人没实名、签字没完成”。**
>
> 只要 R4 环境条件与签字链补齐，后续推进就可以从仓库整理阶段切换为真实交付执行阶段。
