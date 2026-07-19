# G2-B3 发布 / 回滚包

> 适用阶段：G2 正式商用 GA
>
> 用途：把正式商用候选的发布步骤、回滚边界、失败处置和 smoke 验证整理成一个可交接的最小发布 / 回滚包，确保正式 GA 不只是冻结了候选，也不只是演练过，而是可以按统一口径执行发布与回滚。

---

## 1. 目标

G2-B3 的目标是：

> **把正式商用 GA 的发布 / 回滚流程冻结成一个可执行、可复验、可交接的包。**

这一步不负责长周期运维，也不负责企业级 HA；它只负责：

- 发布步骤清楚；
- 回滚步骤清楚；
- 发布失败后知道怎么停、怎么回、怎么留证；
- smoke 验证与异常处置口径统一。

---

## 2. 发布输入

本包默认依赖的输入如下：

- G2-B1 候选冻结结果；
- G2-B2 目标环境演练结果；
- `docs/RELEASE_RUNBOOK_V1.md`；
- `docs/ENVIRONMENT_BASELINE_V1.md`；
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`；
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`；
- `docs/DELIVERY_MATERIALS_INDEX_V1.md`。

---

## 3. 发布步骤

### 3.1 发布前确认

发布前必须确认：

1. 当前候选已经冻结；
2. 目标环境演练通过；
3. 远端 CI 全绿；
4. 交付材料入口完整；
5. 试点边界与已知问题已知；
6. 发布 / 回滚责任人明确。

### 3.2 发布执行

按 runbook 中的最小步骤执行：

```powershell
cd deploy\compose
docker compose up -d --build postgres redis qdrant litellm langfuse
docker compose up -d --build api worker web
docker compose ps
```

### 3.3 发布后 smoke

```powershell
curl.exe -f http://localhost:8000/health
curl.exe -f http://localhost:8000/ready
curl.exe -f http://localhost:3000
```

并确认：
- 登录可用；
- 工作台可用；
- Run Console 可打开；
- Goal Board 可打开。

---

## 4. 回滚边界

### 4.1 何时应回滚

满足以下任一情况时，优先考虑回滚：

- /health 或 /ready 不通过；
- 登录失败且非单点账号问题；
- worker 无法持续消费；
- 核心 run / workflow 链路失败；
- 数据迁移后出现无法接受的异常；
- smoke 不通过且短时间内无法恢复。

### 4.2 回滚目标

回滚目标必须是：
- 上一个已知可用候选；
- 与发布候选区分明确；
- 不依赖未冻结工作树内容。

---

## 5. 回滚步骤

### 5.1 无 DB 迁移影响

```powershell
git checkout <previous-release-tag-or-commit>
cd apps\web
npm ci
npm run build

cd ..\..\deploy\compose
docker compose up -d --build api worker web
docker compose ps
```

### 5.2 需要恢复 DB

```powershell
cd deploy\compose
docker compose stop api worker web
```

恢复备份：

```powershell
docker compose exec -T postgres dropdb --if-exists -U xagent xagent
docker compose exec -T postgres createdb -U xagent xagent
Get-Content backups\<backup-file>.sql | docker compose exec -T postgres psql -U xagent xagent
```

然后切回上一版本并重新启动：

```powershell
git checkout <previous-release-tag-or-commit>
cd ..\..\apps\web
npm ci
npm run build

cd ..\..\deploy\compose
docker compose up -d --build api worker web
```

---

## 6. 失败处置

### 6.1 发布失败

如果发布过程中任一步失败：
1. 立即停止继续扩大范围；
2. 保留 `api` / `worker` / `web` 日志；
3. 记录失败点；
4. 判断是否需要回滚；
5. 若需回滚，按上节执行。

### 6.2 smoke 失败

如果 smoke 失败：
1. 记录 `/health`、`/ready`、前端入口结果；
2. 记录相关日志；
3. 判断是配置、依赖还是代码问题；
4. 不能在未留证的情况下继续试错。

---

## 7. 现有证据入口

当前可直接引用的证据：

- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/coordination/reports/R12_SQLITE_ALEMBIC_DRIFT_GUIDE.md`
- `docs/coordination/reports/R13_CHAT_SSE_FULL_FLOW_E2E.md`
- `docs/coordination/reports/commercialization-g2-b2-target-rehearsal-package.md`
- `docs/coordination/reports/commercialization-goal-board.md`

---

## 8. 完成定义

G2-B3 只有在以下条件同时成立时，才算完成：

- 发布步骤可以按统一口径执行；
- 回滚步骤可以按统一口径执行；
- 发布失败 / smoke 失败有明确处置边界；
- 证据可以回填到发布材料包；
- G2 候选不会因为发布文档而漂移。

---

## 9. 当前结论

G2-B3 的作用不是扩张系统，而是：

> **把正式商用 GA 的发布 / 回滚流程冻结为一套可交接、可留证、可执行的最小闭环。**

完成 G2-B3 后，G2 就具备进入签字 / 证据包阶段的完整发布动作基础。