# G2-B2 目标环境演练包

> 适用阶段：G2 正式商用 GA
>
> 用途：把正式商用候选在目标环境 / full-mode 下的演练步骤、证据要求、发布 / 回滚 / smoke 闭环整理成一个可执行包，确保 G2 不只是“冻结了候选”，而是真的能在目标环境里走通一次完整演练。

---

## 1. 目标

G2-B2 的目标是：

> **在目标环境或等价 full-mode 环境中，完成一次可追踪、可回滚、可复验的正式候选演练。**

这一步不负责签字，不负责把系统永久改成企业长期运营形态；它只负责证明：

- 候选可以在目标环境运行；
- 发布步骤可执行；
- smoke 可通过；
- 失败时可以按 runbook 回滚；
- 证据可以被留档。

---

## 2. 演练输入

演练前必须明确以下输入：

- 当前候选分支 / commit / PR（来自 G2-B1 冻结包）；
- 目标环境类型：dev / staging / prod / 等价 full-mode；
- 环境基线来源：`docs/ENVIRONMENT_BASELINE_V1.md`；
- 发布 / 回滚手册来源：`docs/RELEASE_RUNBOOK_V1.md`；
- 当前真实状态来源：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`；
- 交付材料入口：`docs/DELIVERY_MATERIALS_INDEX_V1.md`。

---

## 3. 演练前 Gate

### 3.1 候选冻结已完成

必须确认：
- G2-B1 候选已冻结；
- 当前正式 GA 只指向唯一候选对象；
- 不再以脏工作树或未提交内容作为演练对象。

### 3.2 环境与 secret 已显式提供

必须确认：
- `XAGENT_SECURITY__JWT_SECRET` 已显式配置；
- `XAGENT_CORS_ORIGINS` 已显式配置；
- `LANGFUSE_NEXTAUTH_SECRET` / `LANGFUSE_SALT` / `LANGFUSE_INIT_USER_PASSWORD` 已显式配置；
- 至少一条真实 LLM 路径可达；
- 不依赖默认管理员 `admin/admin`。

### 3.3 质量门禁可执行

必须确认：
- backend `ruff check` / `pytest` 可执行；
- frontend `lint` / `typecheck` / `build` 可执行；
- 已有至少一组关键 E2E 可作为 smoke / 发布证据。

---

## 4. 演练步骤

### 4.1 发布前准备

1. 锁定当前候选 commit / PR；
2. 记录目标环境；
3. 准备 `.env` 或 secret manager 配置；
4. 确认当前候选对应 CI 结果为绿；
5. 备份数据库与必要数据卷。

### 4.2 构建与部署

按 runbook 的最小路径执行：

```powershell
cd apps/web
npm ci
npm run build

cd ../../deploy/compose
Copy-Item .env.example .env
# 填入真实 secret 与环境地址
docker compose --env-file .env config --quiet
docker compose up -d --build postgres redis qdrant litellm langfuse
docker compose up -d --build api worker web
docker compose ps
```

### 4.3 Smoke 验证

```powershell
curl.exe -f http://localhost:8000/health
curl.exe -f http://localhost:8000/ready
curl.exe -f http://localhost:3000
```

再补充至少一条主链 smoke：
- 登录；
- 进入工作台；
- 打开 Goal Board；
- 打开 Run 详情。

### 4.4 迁移验证

```powershell
cd deploy\compose
docker compose run --rm api python -m alembic current
docker compose run --rm api python -m alembic upgrade head
docker compose run --rm api python -m alembic current
```

### 4.5 发布后恢复演练

按 runbook 模拟一次失败或回滚条件：
1. 记录故障现象；
2. 导出日志；
3. 判断是否需要回滚；
4. 按 runbook 执行回滚；
5. 再次 smoke；
6. 记录恢复结果。

---

## 5. 证据要求

演练必须保留以下证据：

- 版本号 / commit / PR；
- CI run 链接；
- 目标环境说明；
- 部署日志；
- `docker compose ps` 输出；
- `/health`、`/ready` 返回；
- smoke 截图或命令输出；
- 迁移输出；
- 回滚日志（若发生）；
- 最终结论。

证据应最终汇总到：
- `docs/coordination/reports/auto-delivery-phase1-report.md`
- `docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md`

---

## 6. 现有证据入口

可直接复用的材料：

- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`
- `docs/coordination/reports/auto-delivery-phase1-report.md`

---

## 7. 完成定义

G2-B2 只有在以下条件同时成立时，才算完成：

- 目标环境 / full-mode 演练步骤明确；
- 发布 / 回滚 / smoke / migration 都能按 runbook 执行；
- 证据已经保留；
- 演练结果能回填到发布材料包；
- G2 候选对象没有漂移。

---

## 8. 当前结论

G2-B2 的作用不是新增能力，而是：

> **证明正式商用 GA 的唯一候选对象可以在目标环境中被真实演练，并且出现问题时有明确恢复路径与证据。**

完成 G2-B2 后，G2 将具备进入签字 / 证据包阶段的基础。