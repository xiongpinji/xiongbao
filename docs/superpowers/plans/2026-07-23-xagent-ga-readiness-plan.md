# X-Agent 正式商用 GA 收口实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）来跟踪进度。

**目标：** 将 X-Agent 从当前可内部试点 / 受控私有部署状态收口为正式商用 GA，首发范围限定为 Web 工作台、短剧自由画布、企业鉴权与单实例 Docker Compose `full` 部署。

**架构：** 先处理密钥和候选范围，再修复质量门禁与可复现入口；随后在隔离 staging 环境验证完整 Compose 依赖链、真实 provider、E2E、安全、恢复、升级回滚和 50 并发容量；最后以版本 tag、证据包和四类角色签字作为 GA 出口。Helm/Kubernetes、Tauri、多实例 HA 和跨历史版本升级不进入本计划门禁。

**技术栈：** Python 3.11、FastAPI、pytest、Ruff、mypy、Docker Compose、Postgres、Redis、Qdrant、Langfuse、LiteLLM、React 18、Vite、TypeScript、ESLint、Playwright、Locust、GitHub Actions。

---

## 文件与证据结构

### 将修改的代码与配置

- 修改：`.github/workflows/ci.yml` —— 让 mypy 失败阻断 CI，并统一可复现检查入口。
- 修改：`apps/api/pyproject.toml` —— 修复包/测试入口配置，保持 pytest 可从文档指定目录直接执行。
- 修改：`apps/api/xagent/enterprise/authz/openfga.py` —— 消除 OpenFGA 可选客户端的类型错误。
- 修改：`apps/api/xagent/adapters/tools/composio_provider.py` —— 修正工具列表类型协变问题。
- 修改：`apps/api/xagent/adapters/knowledge/__init__.py` —— 明确知识库可选适配器的空值分支。
- 修改：`apps/api/xagent/infra/cache.py` —— 统一 Redis bytes/string 返回类型。
- 修改：`apps/api/xagent/domains/creative_studio/media/video_providers.py` —— 修正 provider 配置映射类型。
- 修改：`apps/api/xagent/domains/open_source_discovery/engine.py` —— 修正候选索引类型。
- 修改：`apps/api/xagent/scripts/ollama_warmup.py` —— 修正 completion 参数及计数类型。
- 修改：`apps/api/xagent/api/v1/creative_studio.py` —— 增加返回结构的显式类型。
- 修改：`apps/api/xagent/core/workflow/engine.py` —— 对并发结果的异常分支做类型收窄。
- 修改：`apps/api/xagent/api/v1/tasks.py` —— 处理可选结果赋值。
- 修改：`apps/api/xagent/api/v1/agents.py` —— 增加验证摘要类型。
- 修改：`apps/api/tests/conftest.py` 或 `apps/api/pyproject.toml` —— 让 `pytest -q` 从 `apps/api` 目录直接可运行。

### 将创建的测试与验证材料

- 创建或修改：`apps/api/tests/test_type_contracts.py` —— 覆盖本次修复的关键静态类型边界。
- 修改：`tests/e2e/playwright.config.*` 及关键 spec —— 支持 staging API/Web 地址与显式账号，不写入 secret。
- 修改：`tests/security/scan.py` —— 支持 `--host`、staging 租户/账号输入和证据输出路径。
- 修改：`tests/load/locustfile.py` —— 固化 50 并发测试参数、结果 CSV 和关键指标输出。
- 创建：`docs/ga/evidence/` 下的 staging、恢复、容量、发布证据索引文件。
- 创建：`docs/ga/GA_RELEASE_MANIFEST.md` —— GA 版本、范围、兼容性、已知限制和证据索引。
- 创建：`docs/ga/GA_SIGNOFF.md` —— TL、QA、DevOps、Owner 签字表。

### 将更新的发布文档

- 修改：`README.md` —— 与 GA 实际状态一致，保留明确不纳入范围。
- 修改：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md` —— 仅在全部门禁真实通过后更新 GA 结论。
- 修改：`docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md` —— 绑定本次候选证据和四类签字。
- 修改：`docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md` —— 从试点口径更新为 GA 后不承诺范围。
- 修改或创建：`docs/RELEASE_RUNBOOK_V1.md` —— 增加 staging 验收、相邻版本升级、回滚、smoke 和支持路径。
- 修改：`docs/ENVIRONMENT_BASELINE_V1.md` —— 明确 staging Compose 是唯一 GA 证据环境。

---

## 任务 1：建立 GA 候选边界并执行密钥止血

**依赖：** 无。必须最先完成。

**文件：**
- 检查：`xagent/.env`、`xagent/deploy/compose/.env`、`xagent/deploy/compose/.env.*`
- 检查：`.gitignore`、`git ls-files`
- 修改：`docs/ga/GA_RELEASE_MANIFEST.md`
- 修改：`docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`

- [ ] **步骤 1：盘点并撤销暴露的 provider key**

运行：

```powershell
rg -n "sk-[A-Za-z0-9]|ark-[A-Za-z0-9]|API_KEY=" . --glob '!node_modules/**' --glob '!dist/**'
```

在 provider 控制台撤销 `xagent/.env` 中出现过的 DeepSeek、图像和视频 key，生成新的 staging key，并确认旧 key 返回无权限。不得把新 key 写入仓库文件。

- [ ] **步骤 2：确认敏感文件不在版本控制中**

运行：

```powershell
git ls-files -- .env* deploy/compose/.env*
git check-ignore -v .env .env.hybrid .env.rehearsal deploy/compose/.env
```

预期：只列出 `.env.example` 文件；所有真实环境文件均被忽略。

- [ ] **步骤 3：建立首发范围清单**

在 `docs/ga/GA_RELEASE_MANIFEST.md` 记录纳入的 Web 页面、API/worker/web Compose 形态、短剧画布、企业鉴权/租户/审计、真实 provider 要求，以及不纳入的 Helm、Tauri、HA、跨历史版本升级。

- [ ] **步骤 4：检查候选工作区并隔离无关改动**

运行：

```powershell
git status --short --branch
git diff --stat
git ls-files --others --exclude-standard
```

将无关实验产物移出 GA 候选或明确在 manifest 中排除；不得删除用户未授权的工作。

- [ ] **步骤 5：Commit**

```powershell
git add docs/ga/GA_RELEASE_MANIFEST.md docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md
git commit -m "docs: define xagent GA release boundary"
```

---

## 任务 2：修复后端类型门禁并使测试入口可复现

**依赖：** 任务 1 的范围确认；密钥不参与本任务测试。

**文件：** 见“将修改的代码与配置”中的后端文件；测试：`apps/api/tests/test_type_contracts.py`。

- [ ] **步骤 1：记录当前失败基线**

运行：

```powershell
mypy xagent --ignore-missing-imports
```

预期：当前基线为 16 个错误；将完整输出保存到任务证据，不修改代码以掩盖错误。

- [ ] **步骤 2：为关键可选适配器和 provider 边界写失败测试**

在 `apps/api/tests/test_type_contracts.py` 覆盖：无 OpenFGA 客户端时返回安全拒绝/明确降级；无知识库客户端时返回既定空结果；Redis 缓存字符串边界返回 `str | None`；provider 配置输出符合声明类型。测试必须使用现有 fixture 和 mock，不调用真实 provider。

- [ ] **步骤 3：逐文件修复类型错误**

按 mypy 输出修复 `openfga.py`、`composio_provider.py`、`knowledge/__init__.py`、`cache.py`、`video_providers.py`、`open_source_discovery/engine.py`、`ollama_warmup.py`、`creative_studio.py`、`workflow/engine.py`、`tasks.py`、`agents.py`。保持运行时行为不变：只增加类型收窄、显式注解、bytes 解码和异常分支处理，不引入新依赖。

- [ ] **步骤 4：移除 CI 的类型错误吞没**

修改 `.github/workflows/ci.yml`，将：

```yaml
run: mypy xagent --ignore-missing-imports || true
```

改为：

```yaml
run: mypy xagent --ignore-missing-imports
```

- [ ] **步骤 5：修复 pytest 入口**

优先在 `apps/api/pyproject.toml` 配置测试运行时的 import 路径；若项目工具链不支持该配置，则在 `apps/api/tests/conftest.py` 使用标准路径注入方式。目标是从 `apps/api` 目录直接运行 `pytest -q`，不依赖临时设置 `PYTHONPATH`。

- [ ] **步骤 6：运行后端门禁**

运行：

```powershell
ruff check xagent tests
mypy xagent --ignore-missing-imports
pytest -q
```

预期：三条命令均退出码 0；pytest 无收集错误、无失败、无超时。

- [ ] **步骤 7：Commit**

```powershell
git add .github/workflows/ci.yml apps/api/pyproject.toml apps/api/xagent apps/api/tests
git commit -m "fix: enforce backend GA quality gates"
```

---

## 任务 3：固化前端、E2E 与安全扫描门禁

**依赖：** 任务 2。

**文件：**
- 修改：`tests/e2e/playwright.config.*`、关键 `tests/e2e/specs/*`
- 修改：`tests/security/scan.py`
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：确认当前前端门禁基线**

运行：

```powershell
npm run lint
npm run typecheck
npm run build
npm audit --omit=dev --audit-level=high
```

预期：全部通过；若全量 audit 的 dev/build 工具链仍有告警，记录版本、影响和 GA 处置结论，不把生产依赖结果冒充全量无风险。

- [ ] **步骤 2：参数化 Playwright 环境**

使 E2E 使用 `E2E_BASE_URL`、`XAGENT_DEV_API_TARGET`、`E2E_USERNAME`、`E2E_PASSWORD`，默认值仅用于本地；staging 运行时从 CI secret 注入账号，测试输出不得打印密码或 token。

- [ ] **步骤 3：覆盖 GA 关键链路**

确保关键 spec 覆盖登录、对话/SSE、运行详情、工作流、短剧自由画布、设置、失败态与重试；每个场景使用唯一测试数据并在 teardown 清理可清理资源。

- [ ] **步骤 4：参数化安全扫描**

使 `tests/security/scan.py` 支持 staging host、显式测试账号和结果文件；验证健康探针例外、业务端点鉴权、跨租户头注入、租户记忆隔离、SQL 注入、限流和安全响应头。

- [ ] **步骤 5：运行本地集成门禁**

运行：

```powershell
python tests/security/scan.py --host http://localhost:8000
cd tests/e2e
npm ci
npx playwright test --project=chromium
```

预期：安全扫描全部 PASS；关键 E2E 无失败。未运行服务时必须报告环境阻断，不得伪造通过。

- [ ] **步骤 6：Commit**

```powershell
git add tests/e2e tests/security .github/workflows/ci.yml
 git commit -m "test: harden GA integration and security gates"
```

---

## 任务 4：准备并执行 staging Compose full 演练

**依赖：** 任务 3；需要 staging 主机、域名/TLS 终止方案、secret manager/CI secrets、真实三类 provider。

**文件：**
- 检查：`deploy/compose/docker-compose.yml`、`deploy/compose/.env.example`
- 修改：`docs/ENVIRONMENT_BASELINE_V1.md`、`docs/RELEASE_RUNBOOK_V1.md`
- 创建：`docs/ga/evidence/staging-full-rehearsal.md`

- [ ] **步骤 1：校验 staging 配置**

使用 secret manager 注入环境变量，运行：

```powershell
cd deploy/compose
docker compose --env-file .env config --quiet
```

预期：退出码 0；不在命令输出中打印 secret。

- [ ] **步骤 2：从零启动 Compose full**

运行：

```powershell
docker compose --env-file .env down --volumes --remove-orphans
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
```

预期：api、worker、web、Postgres、Redis、Qdrant、Langfuse、LiteLLM 均达到预期健康状态；记录镜像 digest、版本、启动耗时和异常日志。

- [ ] **步骤 3：执行 staging 核心验收**

验证 `/health`、`/ready`、显式账号登录、文本主链、工作流、Run Console、短剧画布、失败重试恢复、真实 LLM/图像/视频 provider。将命令、时间、结果、截图和脱敏日志写入 `docs/ga/evidence/staging-full-rehearsal.md`。

- [ ] **步骤 4：执行 staging E2E 与安全扫描**

运行：

```powershell
python tests/security/scan.py --host https://<staging-api>
cd tests/e2e
$env:E2E_BASE_URL='https://<staging-web>'
npx playwright test --project=chromium
```

预期：全部通过；证据文件不包含 secret、token 或用户密码。

- [ ] **步骤 5：补齐发布与回滚 Runbook**

在 `docs/RELEASE_RUNBOOK_V1.md` 固化 Compose 配置校验、部署、数据库迁移、smoke、停止、回滚、日志导出和失败升级路径，并明确相邻 GA 版本限制。

- [ ] **步骤 6：Commit 演练材料**

```powershell
git add docs/ENVIRONMENT_BASELINE_V1.md docs/RELEASE_RUNBOOK_V1.md docs/ga/evidence/staging-full-rehearsal.md
git commit -m "docs: record staging full GA rehearsal"
```

只提交脱敏证据和文档，不提交 `.env`、日志中的 token 或导出的数据库。

---

## 任务 5：验证备份恢复、相邻版本升级与回滚

**依赖：** 任务 4 的 staging full 数据。

**文件：**
- 检查/修改：`scripts/backup.py`、数据库迁移文件、`docs/RELEASE_RUNBOOK_V1.md`
- 创建：`docs/ga/evidence/recovery-upgrade-rollback.md`

- [ ] **步骤 1：执行 Postgres/Qdrant/审计数据备份**

使用项目现有 `scripts/backup.py` 和数据库/Qdrant 官方备份命令，生成带时间戳的备份；记录备份大小、完成时间和校验摘要，脱敏后保存证据。

- [ ] **步骤 2：在隔离恢复目标执行恢复**

恢复到隔离 Compose 环境，验证用户/租户、工作流、运行记录、Qdrant 记忆和审计链数据完整性。记录恢复开始/结束时间，计算 RTO；以最近可恢复备份时间计算 RPO。

- [ ] **步骤 3：执行相邻 GA 版本升级**

从上一 GA tag 启动 staging，先备份，再切换当前候选镜像，执行 Alembic migration，验证核心链路和数据完整性。不得跳过 migration 输出。

- [ ] **步骤 4：执行失败回滚**

在隔离环境模拟升级后 smoke 失败，按 Runbook 恢复备份并回退上一 GA 镜像；验证系统可用、数据未丢失、审计链可追溯。

- [ ] **步骤 5：确认基线**

必须达到 RPO ≤24 小时、RTO ≤4 小时；否则阻断 GA，不通过降低口径解决。将步骤、耗时、数据校验、失败点和责任人写入证据文件。

- [ ] **步骤 6：Commit**

```powershell
git add docs/RELEASE_RUNBOOK_V1.md docs/ga/evidence/recovery-upgrade-rollback.md scripts/backup.py
 git commit -m "docs: verify GA recovery and rollback baseline"
```

---

## 任务 6：执行 50 并发容量基线

**依赖：** 任务 4 staging full 已稳定，任务 5 不得存在未解释的数据风险。

**文件：**
- 修改：`tests/load/locustfile.py`
- 创建：`docs/ga/evidence/capacity-50-concurrency.md`
- 修改：`docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`

- [ ] **步骤 1：固化负载参数和指标出口**

Locust 场景固定覆盖登录、角色列表、agent 运行、记忆检索、开源发现和短剧草稿；支持 `USERS=50`、`SPAWN_RATE=5`、`DURATION=60s`，输出 CSV 和 JSON 摘要，不输出 token。

- [ ] **步骤 2：运行 50 并发测试**

运行：

```powershell
locust -f tests/load/locustfile.py --host https://<staging-api> --headless -u 50 -r 5 -t 60s --csv docs/ga/evidence/capacity-50-concurrency
```

记录 API P95、错误率、429 比例/阈值、worker backlog、任务耗时/失败率以及 DB/Redis/Qdrant/LLM 资源瓶颈。

- [ ] **步骤 3：形成容量边界**

在证据文档中明确 50 并发是否通过、超出基线时的行为、限流方式、扩容建议和不承诺超过 50 并发固定 SLA。任何未解释错误均阻断 GA。

- [ ] **步骤 4：Commit**

```powershell
git add tests/load/locustfile.py docs/ga/evidence/capacity-50-concurrency.md docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md
git commit -m "test: establish GA capacity baseline"
```

---

## 任务 7：组装发布证据、签字并发布候选

**依赖：** 任务 1-6 全部通过。

**文件：**
- 创建：`docs/ga/GA_RELEASE_MANIFEST.md`
- 创建：`docs/ga/GA_SIGNOFF.md`
- 修改：`docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- 修改：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 修改：`README.md`
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`

- [ ] **步骤 1：建立证据矩阵**

为每个 P0-A 至 P0-G 填写证据文件、候选 commit/tag、执行时间、执行人、结果和复核人；`REVIEW` 或 `READY` 不得标记为通过。

- [ ] **步骤 2：生成版本 manifest**

记录版本号、Git tag、候选 commit、数据库迁移 head、部署镜像、首发范围、不支持范围、provider 验收结果、兼容性和回滚限制。

- [ ] **步骤 3：执行候选全量验证**

在候选 tag 上重新运行：

```powershell
ruff check apps/api/xagent apps/api/tests
cd apps/api; pytest -q; mypy xagent --ignore-missing-imports
cd ../web; npm ci; npm run lint; npm run typecheck; npm run build
cd ../..; python scripts/license_check.py
```

预期：全部退出码 0，输出和候选 tag 一致。

- [ ] **步骤 4：完成四类角色签字**

在 `docs/ga/GA_SIGNOFF.md` 由 TL、QA、DevOps、Owner 分别确认范围、质量、安全、环境、恢复、容量和支持承诺；任何角色拒签都阻断发布。

- [ ] **步骤 5：更新公开状态口径**

只有签字完成后，才将事实源、README、发布检查表和交付索引更新为 GA；否则保持“内部试点/受控私有部署候选”。

- [ ] **步骤 6：创建 GA tag 并执行发布后 smoke**

```powershell
git tag -a v<GA_VERSION> -m "release: xagent GA <GA_VERSION>"
git show --stat --oneline v<GA_VERSION>
```

发布后重新验证 `/health`、`/ready`、登录、文本主链、Run Console、画布和 metrics，进入既定观察窗口。

---

## 总体验证命令

在声称 GA 前，必须取得本次候选的新鲜输出：

```powershell
cd apps/api
ruff check xagent tests
mypy xagent --ignore-missing-imports
pytest -q

cd ../web
npm ci
npm run lint
npm run typecheck
npm run build

cd ../..
python scripts/license_check.py
python tests/security/scan.py --host https://<staging-api>
cd tests/e2e
npx playwright test --project=chromium
```

另须存在脱敏且可复核的 staging full、恢复/回滚、升级和 50 并发证据。任何命令未执行、环境未达到、结果未归档或角色未签字，都只能报告为 GA 准备中。

## 计划自检

- 规格范围映射：首发范围/排除项由任务 1、4、7 覆盖；安全由任务 1、3、4 覆盖；类型与测试由任务 2、3、7 覆盖；staging full 由任务 4 覆盖；恢复/RPO/RTO/相邻升级由任务 5 覆盖；50 并发由任务 6 覆盖；支持/签字/发布由任务 7 覆盖。
- 依赖完整：任务 1 无依赖；任务 2 依赖 1；任务 3 依赖 2；任务 4 依赖 3；任务 5/6 依赖 4；任务 7 依赖全部前置任务。
- 占位符检查：`<staging-api>`、`<staging-web>`、`<GA_VERSION>` 是执行时从 staging 和版本决策得到的具体参数，不是代码实现占位；执行前必须替换并记录实际值。
- 安全检查：所有真实 secret 只通过控制台/secret manager 注入，不进入计划证据、Git、日志或截图。
