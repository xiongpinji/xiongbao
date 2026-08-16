# X-Agent GA 收口阶段 1 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在不合并、不发布、不部署、不调用付费模型的边界内，为 PR #22 的候选提交完成独立审查、剩余本地发布门禁和条件跳过分类，并把 Critical / Important 问题修到可复验状态。

**架构：** 以候选提交 SHA 为证据主键，审查与每类门禁分别产出可追溯证据。若源代码发生变化，旧 SHA 证据立即降级为历史证据，在新 SHA 上重跑受影响门禁和五门聚合；远端 PR、签名 RC、staging 和客户 UAT 留到后续授权阶段。

**技术栈：** Git / GitHub Actions、Python 3.11 / pytest / FastAPI、Node.js / Promptfoo、Docker Desktop / Docker Scout 或 Trivy、k6、PowerShell。

**本机 Python 适配：** 系统 Python 的全局 `site-packages/_editable_impl_xagent.pth` 是 UTF-8 中文路径，但 Python 3.11 在当前 Windows locale 下按 GBK 读取而启动失败。已用 `python.exe -S -m venv` 在当前 worktree 的 `apps/api/.venv` 创建 Python 3.11.9 隔离环境，并以非 editable 方式安装当前源码及 `dev,sandbox,tts,editor` extras；所有本地 Python 门禁必须使用该环境，避免导入共享工作区源码。

---

## 范围和基线

- 实际工作树：`D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\commercial-delivery-20260815`
- 分支：`codex/commercial-delivery-20260815`
- PR：`#22`
- Base：`c8898ca16ea2cc1ac0f88d6b1948f8f9755cc48d`
- Head：`90a8c54a54c574839a7e1820f84d8de8d0650647`
- 已授权：本地只读审查、本地门禁、本地必要修复及复验。
- 未授权：合并、推送、创建 Release / tag、发布镜像、staging / 生产部署、付费模型调用、客户数据写入。
- 受保护运行中项目：不得停止、重建或改写 `ai-moive-studio` 的 `aicg-minio`、`aicg-postgres` 及其卷。

## 文件结构

- 创建：`docs/superpowers/plans/2026-08-16-xagent-ga-closure-phase-1.md` —— 本阶段范围、步骤和验收合同。
- 生成但不提交：`output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/` —— 审查、负载、Promptfoo、镜像与跳过项证据。
- 可能修改：仅限独立审查或门禁证明为 Critical / Important 的源文件和对应测试；发现前不预设实现文件。

## 总体验收标准

- 独立审查没有未解决的 Critical / Important；每条结论包含 `file:line` 和证据。
- k6 脚本全部阈值通过：业务流 `p95 < 350 ms`、`p99 < 800 ms`、错误率 `< 5%`、检查率 `> 99%`；指标抓取 `p95 < 500 ms`、错误率 `< 0.1%`、检查率 `> 99.9%`；自定义 API 延迟 `p95 < 300 ms`。
- Promptfoo 固定 `0.122.0`，8/8 用例通过结果校验器，真实命中本地 API 的认证、租户与产品输出合同；不调用外部模型。
- API 和 Web Dockerfile 在当前 SHA 构建成功；对本地镜像执行高危 / 严重漏洞扫描，结果可归档且无未处置的可修复 Critical / High。
- 对本轮 pytest 条件跳过逐项形成矩阵：`executed_passed`、`accepted_optional` 或 `blocked_environment`，不得用总数代替原因。
- 若有代码修复：先有可复现失败测试，再做最小修复；新 SHA 上受影响测试、五门本地聚合和远端同 SHA CI 都需要重新建立，未推送前只能称本地候选。

## 执行状态（2026-08-16）

- `90a8c54...` 上的 k6 门禁已实际通过：12,733 iterations、339.3 req/s、p95 273.3 ms、p99 491.0 ms、0.00% errors；由于随后发生代码修复，该证据降级为历史证据，最终提交必须重跑。
- Promptfoo 固定版本实际执行了 8 个请求。虽然原计划要求不调用外部模型，但本机既有 provider 配置把请求路由到了 `deepseek-v4-flash`，构成 8 次未预期真实外部调用；发现后立即停止 API 且未重试。后续 live eval 状态为 `needs_authorization`，静态合同测试通过不能替代该门禁。
- Promptfoo 的 8 个请求均返回 `status=succeeded`、非空 `run_id`、非空回答和正确租户；旧断言错误要求回答逐字回显查询，造成 0/8。合同已改为验证 query 进入 `goal` 且回答非空，并明确不把对抗输入 smoke 宣称为安全策略验收。
- Python 3.11.9 隔离环境下，Docker sandbox 集成 8/8 通过；媒体 optional 节点均执行通过；仅两个 Windows 符号链接节点因 WinError 1314 / 当前进程无创建符号链接权限而保持 `blocked_environment`。
- 五轮独立审查确认并推动修复：Compose / Qdrant / baseline worktree 残留、同 SHA 并发资源误删风险、cleanup 覆盖主错误、备份恢复 nonce 合同断裂、本地门禁误选 Python 3.13，以及子 Agent 取消挂起。最终复审无 Critical / Important。
- 完整后端商用回归收集 898 项：888 通过、10 跳过、退出码 0；其中 8 项 Docker 跳过已用显式集成开关另行执行为 8/8 通过，剩余 2 项为 Windows 符号链接权限阻断。

### 任务 1：锁定基线并完成独立代码审查

**文件：**
- 读取：`docs/superpowers/plans/2026-08-15-xagent-commercial-delivery-program.md`
- 读取：`docs/superpowers/plans/2026-08-15-xagent-commercial-kernel.md`
- 读取：`docs/superpowers/plans/2026-08-15-xagent-webapi-delivery-gate.md`
- 读取：`docs/superpowers/plans/2026-08-15-xagent-desktop-delivery-gate.md`
- 读取：`docs/superpowers/plans/2026-08-15-xagent-same-sha-evidence-rollback.md`
- 生成：`output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/review.md`

- [ ] **步骤 1：确认 worktree、分支、Base、Head、PR head 和工作区状态**

运行：

```powershell
git rev-parse --git-dir
git rev-parse --git-common-dir
git branch --show-current
git rev-parse HEAD
git status --short
gh pr view 22 --json baseRefOid,headRefOid,state,mergeable,mergeStateStatus,reviewDecision
```

预期：linked worktree；分支为 `codex/commercial-delivery-20260815`；本任务开始时 Head 与 PR head 均为 `90a8c54...`；除本计划外无非预期修改。

- [ ] **步骤 2：派遣独立 reviewer 审查 Base..Head**

运行：

```powershell
git diff --stat c8898ca16ea2cc1ac0f88d6b1948f8f9755cc48d..90a8c54a54c574839a7e1820f84d8de8d0650647
git diff --check c8898ca16ea2cc1ac0f88d6b1948f8f9755cc48d..90a8c54a54c574839a7e1820f84d8de8d0650647
```

预期：`git diff --check` 退出码为 0；reviewer 返回按 Critical / Important / Minor 分级的具体结论和是否可合并判断。

- [ ] **步骤 3：逐条复核 reviewer 发现**

运行：对每个发现打开实际文件与测试，并用最小复现命令验证。误报在 `review.md` 记录反证；Critical / Important 转入任务 6。

预期：没有未经本地证据确认的审查结论。

### 任务 2：执行本地 k6 负载门禁

**文件：**
- 读取：`.github/workflows/ci.yml:564`
- 读取：`tests/load/k6-load.js`
- 生成：`output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/load/`

- [ ] **步骤 1：端口与进程预检**

运行：

```powershell
Get-NetTCPConnection -LocalPort 18081 -State Listen -ErrorAction SilentlyContinue
docker ps --format '{{.Names}} {{.Ports}}'
```

预期：`18081` 未占用；不修改任何已有容器。

- [ ] **步骤 2：以 CI 等价环境启动本地 API**

运行：

```powershell
$pythonCommand=(Resolve-Path 'apps/api/.venv/Scripts/python.exe').Path
$env:XAGENT_MODE='lite'
$env:XAGENT_SECURITY__REQUIRE_AUTH='false'
$env:XAGENT_SECURITY__RATE_LIMIT_ENABLED='false'
$env:XAGENT_DB__URL='sqlite+aiosqlite:///./xagent-load-phase1.db'
$api = Start-Process -FilePath $pythonCommand -ArgumentList '-m','uvicorn','xagent.main:app','--host','127.0.0.1','--port','18081' -WorkingDirectory 'apps/api' -WindowStyle Hidden -RedirectStandardOutput 'output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/load/api.stdout.log' -RedirectStandardError 'output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/load/api.stderr.log' -PassThru
Invoke-RestMethod http://127.0.0.1:18081/health
```

预期：健康状态为 `ok`；记录 PID，只停止本步骤启动的进程。

- [ ] **步骤 3：从只读挂载运行官方 k6 镜像**

运行：

```powershell
docker pull grafana/k6:latest
docker image inspect grafana/k6:latest --format '{{index .RepoDigests 0}}'
docker run --rm -v "${PWD}/tests/load:/scripts:ro" grafana/k6:latest run --env BASE_URL=http://host.docker.internal:18081 /scripts/k6-load.js
```

预期：进程退出码为 0，所有 `tests/load/k6-load.js` 阈值均通过；日志与解析后的摘要写入 `load/`。

- [ ] **步骤 4：清理本任务进程**

运行：

```powershell
Stop-Process -Id $api.Id
Get-NetTCPConnection -LocalPort 18081 -State Listen -ErrorAction SilentlyContinue
```

预期：仅本任务 API 被停止，端口释放，受保护容器仍运行。

### 任务 3：执行本地 Promptfoo 质量门禁

**文件：**
- 读取：`.promptfoo/config.yaml`
- 读取：`scripts/check_promptfoo_results.py`
- 生成：`output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/promptfoo/`

- [ ] **步骤 1：生成临时 JWT、迁移隔离数据库并启动认证 API**

运行：

```powershell
$pythonCommand=(Resolve-Path 'apps/api/.venv/Scripts/python.exe').Path
$env:XAGENT_MODE='lite'
$env:XAGENT_SECURITY__REQUIRE_AUTH='true'
$env:XAGENT_SECURITY__JWT_SECRET=[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
$env:XAGENT_DB__URL='sqlite+aiosqlite:///./xagent-promptfoo-phase1.db'
Push-Location apps/api
& $pythonCommand -m alembic upgrade head
Pop-Location
$api = Start-Process -FilePath $pythonCommand -ArgumentList '-m','uvicorn','xagent.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'apps/api' -WindowStyle Hidden -RedirectStandardOutput 'output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/promptfoo/api.stdout.log' -RedirectStandardError 'output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/promptfoo/api.stderr.log' -PassThru
Invoke-RestMethod http://127.0.0.1:8000/ready
```

预期：独立 SQLite 数据库迁移成功，`/ready` 成功；不得覆盖仓库原有 `xagent.db`。

- [ ] **步骤 2：注册隔离租户并保存内存态 token**

运行：

```powershell
$identity='promptfoo-local-' + [Guid]::NewGuid().ToString('N')
$password=[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$body=@{username=$identity;password=$password;tenant_id=$identity} | ConvertTo-Json
$auth=Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/register -ContentType 'application/json' -Body $body
$env:PROMPTFOO_API_TOKEN=$auth.access_token
$env:PROMPTFOO_TENANT_ID=$identity
```

预期：返回 `tenant_id == $identity`、角色包含 `member` 且 token 非空；证据中不得落盘 token 或密码。

- [ ] **步骤 3：运行固定版本 Promptfoo 和结果校验器**

运行：

```powershell
npx --yes promptfoo@0.122.0 eval -c .promptfoo/config.yaml --no-cache --max-concurrency 1 --output output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/promptfoo/results.json
& $pythonCommand scripts/check_promptfoo_results.py output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/promptfoo/results.json --expected 8
```

预期：校验器输出 `promptfoo quality gate passed: 8/8`；所有请求只命中本地 API。

- [ ] **步骤 4：清理进程、敏感环境变量和隔离数据库**

运行：

```powershell
Stop-Process -Id $api.Id
Remove-Item Env:PROMPTFOO_API_TOKEN,Env:PROMPTFOO_TENANT_ID,Env:XAGENT_SECURITY__JWT_SECRET -ErrorAction SilentlyContinue
```

预期：没有 token 写入 Git 跟踪文件；端口 `8000` 释放。隔离数据库作为本轮本地证据保留，最终由 `git status --short` 验证其处于忽略范围。

### 任务 4：构建并扫描本地容器镜像

**文件：**
- 读取：`apps/api/Dockerfile`
- 读取：`apps/web/Dockerfile`
- 生成：`output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/containers/`

- [ ] **步骤 1：构建 Web 静态产物**

运行：

```powershell
Push-Location apps/web
npm ci
npm run build
Pop-Location
```

预期：退出码为 0，`apps/web/dist/` 存在。

- [ ] **步骤 2：使用 SHA 唯一标签构建 API / Web 镜像**

运行：

```powershell
docker build --pull -t xagent-api:ga-phase1-90a8c54 apps/api
docker build --pull -t xagent-web:ga-phase1-90a8c54 apps/web
docker image inspect xagent-api:ga-phase1-90a8c54 xagent-web:ga-phase1-90a8c54
```

预期：两个镜像构建成功并记录本地 image ID；不 push、不覆盖任何运行中容器。

- [ ] **步骤 3：扫描高危和严重漏洞**

运行：

```powershell
docker scout cves xagent-api:ga-phase1-90a8c54 --only-severity critical,high --format sarif --output output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/containers/api-scout.sarif
docker scout cves xagent-web:ga-phase1-90a8c54 --only-severity critical,high --format sarif --output output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/containers/web-scout.sarif
```

预期：扫描可执行并可归档。所有可修复 Critical / High 必须进入任务 6；若 Scout 因外部账户认证阻断，改用固定版本 Trivy 容器扫描并记录镜像 digest，不能把“无法扫描”写成通过。

### 任务 5：分类并关闭条件跳过

**文件：**
- 读取：`apps/api/tests/test_audio_providers.py`
- 读取：`apps/api/tests/test_docker_sandbox_integration.py`
- 读取：`apps/api/tests/test_file_write_containment.py`
- 读取：`apps/api/tests/test_skill_packages.py`
- 生成：`output/ga-closure/90a8c54a54c574839a7e1820f84d8de8d0650647/skips/matrix.md`

- [ ] **步骤 1：重新收集跳过项和精确原因**

运行：

```powershell
Push-Location apps/api
& '.\.venv\Scripts\python.exe' -m pytest tests/test_audio_providers.py tests/test_docker_sandbox_integration.py tests/test_file_write_containment.py tests/test_skill_packages.py -q -rs
Pop-Location
```

预期：得到当前 SHA 的精确节点、计数和原因，不沿用历史数字。

- [ ] **步骤 2：执行 Docker sandbox 实机集成测试**

运行：

```powershell
Push-Location apps/api
$env:XAGENT_DOCKER_INTEGRATION='1'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_docker_sandbox_integration.py -q -rs
Remove-Item Env:XAGENT_DOCKER_INTEGRATION
Pop-Location
```

预期：测试使用临时容器且退出后无残留；全部通过或形成具体环境阻断证据。

- [ ] **步骤 3：验证可选媒体 extra 的离线行为**

运行：

```powershell
Push-Location apps/api
& '.\.venv\Scripts\python.exe' -m pytest tests/test_audio_providers.py -q -rs
Pop-Location
```

预期：`edge_tts` 调用保持 mock、不访问外网；MoviePy 生成本地测试素材；可选 extra 相关节点通过。若依赖合同本身不可安装，记录为产品打包阻断而非接受跳过。

- [ ] **步骤 4：验证 Windows 符号链接安全用例**

运行：

```powershell
Push-Location apps/api
& '.\.venv\Scripts\python.exe' -m pytest tests/test_file_write_containment.py tests/test_skill_packages.py -q -rs
Pop-Location
```

预期：当前权限能创建符号链接时节点执行通过；不能创建时保存 OS 错误、权限状态和 CI 对应证据，分类为 `blocked_environment`，不得标成测试通过。

- [ ] **步骤 5：编写跳过项矩阵**

预期：每个节点有原始原因、商用相关性、实际执行结果、最终分类和后续责任方；同一节点在多个 gate 中重复出现只计一次。

### 任务 6：修复经证实的 Critical / Important

**文件：**
- 修改：仅限任务 1、2、3、4、5 证明有问题的文件及其直接测试。

- [ ] **步骤 1：为每个问题写最小失败测试或失败命令**

预期：修复前稳定失败，错误与审查 / 门禁发现一致。

- [ ] **步骤 2：实施最小修复**

预期：不做相邻重构，不添加未要求功能；每行修改可追溯到已确认问题。

- [ ] **步骤 3：运行目标测试并检查差异**

运行：

```powershell
git diff --check
git status --short
```

预期：目标测试通过，无格式错误，无密钥或运行数据库进入跟踪集。

- [ ] **步骤 4：为已确认问题补写精确修复附录并提交**

运行：先把该问题的实际文件路径、失败测试、最小实现和验证命令追加到本计划，再按附录列出的精确路径执行 `git add`，最后运行 `git commit -m "fix: close verified GA blocker"`。

预期：不存在问题时本步骤不产生提交；存在问题时，一个提交只处理同一问题族，提交后记录新 SHA，并且提交内容与附录逐项一致。

- [ ] **步骤 5：在新 SHA 重建证据**

运行：受影响门禁、五门本地聚合、任务 2—5 中受影响的发布门禁。

预期：新 SHA 全部通过；旧 SHA 证据保留但明确标为历史证据。未经推送与 Hosted CI 复验，不提升为远端候选。

### 任务 7：阶段 1 审计与交接

**文件：**
- 生成：`output/ga-closure/<最终 SHA>/phase-1-report.md`

- [ ] **步骤 1：核对证据 SHA、命令退出码、残留进程和容器**

运行：

```powershell
git rev-parse HEAD
git status --short
docker ps --format '{{.Names}} {{.Image}} {{.Ports}}'
Get-NetTCPConnection -LocalPort 8000,18081 -State Listen -ErrorAction SilentlyContinue
```

预期：所有证据指向最终 SHA；无本任务残留 API 或临时容器；受保护容器状态未被改变。

- [ ] **步骤 2：形成分级结论**

预期：报告分别列出 `passed`、`accepted_optional`、`blocked_environment`、`needs_authorization`；明确阶段 1 不是 GA、不是 Release、不是部署证明。

- [ ] **步骤 3：确定下一门授权**

预期：若阶段 1 无 Critical / Important，下一步仅请求“推送最终 SHA 并让 PR/Hosted CI 复验”的授权；随后才进入签名 RC、staging、客户 UAT / GA。

## 已确认问题修复附录 A（2026-08-16）

### A1：Promptfoo 产品合同断言不可满足

**实证：** 固定版本 `0.122.0` 真实命中本地 API 共 8 次；认证、隔离租户、`status=succeeded`、`run_id` 和非空回答全部成立，但 `.promptfoo/config.yaml` 要求回答逐字包含原问题，导致 0/8。API 日志同时证明本机既有 provider 配置把请求路由到 `deepseek-v4-flash`；服务已停止，未获新授权前不得再次执行真实 eval。

**文件：**
- 修改：`tests/release/test_r3_promptfoo_contract.py`
- 修改：`.promptfoo/config.yaml`

- [ ] 先把合同测试改为要求 `result.goal.includes(query)` 与 `result.final_answer.trim().length > 0`，并明确拒绝 `result.final_answer.includes(query)`。
- [ ] 运行 `python -m pytest tests/release/test_r3_promptfoo_contract.py -q`，预期因现有配置仍使用旧断言而失败。
- [ ] 最小修改 Promptfoo JavaScript 断言：查询必须进入返回的 `goal`，回答必须为非空字符串；保留成功状态、run id、租户、Traceback 和 500 响应检查。
- [ ] 重跑同一测试，预期全部通过。真实 8/8 复验保持 `needs_authorization`，不得从静态合同测试推断为通过。

### A2：Web/API 与短剧 Compose 门残留项目资源

**实证：** 当前 Docker 主机存在多批历史 `xagent-commercial-*`、`xagent-short-*` 的退出容器和 project-labeled volumes；两个脚本 finally 仅收集日志，没有 teardown。

**文件：**
- 修改：`tests/release/test_gate_script_schema.py`
- 修改：`scripts/run_webapi_commercial_gate.ps1`
- 修改：`scripts/run_short_drama_commercial_gate.ps1`

- [ ] 新增合同测试，要求两个脚本在启动前确认 project 不存在，在启动前设置 cleanup ownership 标记，在 finally 中先核对 container / volume / network 的精确 Compose project label，再执行 `down --remove-orphans --volumes` 并复核 project 不存在。
- [ ] 运行 `python -m pytest tests/release/test_gate_script_schema.py -q`，预期现有脚本缺少上述合同而失败。
- [ ] 在两个脚本中实现最小的 `Assert-ProjectAbsent`、`Assert-ProjectOwnership` 与 `Remove-AuditedComposeProject`，只操作从当前 40 位 source SHA 派生的项目名；任何标签不一致均 fail closed。
- [ ] 重跑合同测试和 PowerShell parser，预期全部通过。

### A3：回滚门残留 Compose 项目与临时 baseline worktree

**实证：** 当前 Docker 主机存在多批历史 `xagent-rollback-candidate-*`、`xagent-restore-*` 的退出容器和 project-labeled volumes；baseline worktree 执行 `npm ci/build` 后只用非 force `git worktree remove`。

**文件：**
- 修改：`tests/release/test_rollback_drill_script.py`
- 修改：`scripts/run_rollback_drill.ps1`

- [ ] 新增合同测试，要求 candidate / restore 两个项目均执行标签保护的 `down --remove-orphans --volumes`，并要求只在 baseline worktree 的绝对父目录等于审计 `.worktrees` 根后执行 `git worktree remove --force`。
- [ ] 运行 `python -m pytest tests/release/test_rollback_drill_script.py -q`，预期现有清理合同缺失而失败。
- [ ] 最小实现两个 Compose 项目的 owner 标记和 finally teardown；将已审计临时 baseline worktree 的移除改为 `worktree remove --force`。
- [ ] 重跑合同测试和 PowerShell parser，预期全部通过。

### A4：清理异常覆盖主错误与同 SHA 并发 ownership 缺口

**实证：** 第二轮独立审查确认，固定 SHA project 名无法区分同 SHA 并发会话；finally 中直接抛 cleanup 错误会覆盖主流程错误，且回滚 restore cleanup 失败会跳过 candidate/worktree/private-state cleanup。

**文件：**
- 修改：`tests/release/test_gate_script_schema.py`
- 修改：`tests/release/test_rollback_drill_script.py`
- 修改：`scripts/run_webapi_commercial_gate.ps1`
- 修改：`scripts/run_short_drama_commercial_gate.ps1`
- 修改：`scripts/run_rollback_drill.ps1`

- [ ] 扩展合同测试，要求 Compose project 名包含每次运行生成的 8 位随机 nonce，并要求脚本分别保存 `$primaryError` 与 `$cleanupErrors`。
- [ ] 运行目标 pytest，预期现有固定名称和直接 finally 抛错实现失败。
- [ ] 最小修改三个脚本：project 名使用 `sha8 + runNonce`；主流程 `catch` 保存原始异常；finally 的日志、各 project teardown、worktree、private state 和 transcript 分别 try/catch 并继续；cleanup 错误落入 evidence。
- [ ] 主流程失败时重抛原始异常；主流程成功但 cleanup 失败时让 gate 失败。重跑目标 pytest 与 PowerShell parser，预期全绿。

### A5：本地五门未锁定 Python 3.11

**实证：** 五个门禁的 `Resolve-PythonCommand` 在当前 worktree 没有 `.venv` 时选中共享 venv；实测该解释器为 Python `3.13.13`，而规格与所有 Hosted CI Python job 固定 `3.11`。

**文件：**
- 修改：`tests/release/test_gate_script_schema.py`
- 修改：`scripts/run_commercial_kernel_gate.ps1`
- 修改：`scripts/run_webapi_commercial_gate.ps1`
- 修改：`scripts/run_short_drama_commercial_gate.ps1`
- 修改：`scripts/run_desktop_commercial_gate.ps1`
- 修改：`scripts/run_rollback_drill.ps1`

- [ ] 新增合同测试，要求五门在解析 Python 后执行 `Assert-Python311`，只接受 `sys.version_info[:2] == (3, 11)`。
- [ ] 运行目标 pytest，预期现有脚本缺少版本断言而失败。
- [ ] 在五门加入最小版本检查；错误信息必须包含实际版本和 `Python 3.11` 期望。
- [ ] 在当前 worktree 建立隔离的 Python 3.11 venv，非 editable 安装当前 API 与门禁所需 extras，避免全局 UTF-8 `.pth` / GBK 冲突和共享 venv 污染。
- [ ] 重跑合同测试、PowerShell parser，并用每个脚本解析出的解释器打印版本，预期均为 `3.11`。

### A6：回滚 nonce 与备份 / 恢复作用域合同不兼容

**实证：** 第三轮独立审查把 `run_rollback_drill.ps1` 生成的 `sha8 + nonce` 名称实际代入 `backup.validate_scope()` / `restore.validate_restore_scope()`，两者仍只接受旧 SHA-only 名称，导致回滚门在备份阶段必然失败。新增函数级合同测试后稳定复现。

**文件：**
- 修改：`scripts/backup.py`
- 修改：`scripts/restore.py`
- 修改：`tests/release/test_backup_restore_safety.py`

- [x] 新增与 PowerShell 完全一致的 candidate / restore Compose 和 Qdrant 正例。
- [x] 新增错 SHA、project / collection nonce 不一致的拒绝用例。
- [x] 用正则解析并绑定 `sha8` 与同一 8 位十六进制 nonce；目标 release tests 通过。

### A7：剪映草稿导出与 pyJianYingDraft 0.3 API 不兼容

**实证：** 在 Python 3.11 隔离环境安装声明的 `editor` extra 后，`tests/test_editor.py::test_export_draft` 真实失败：`ScriptFile` 已没有 `add_track`，0.3 API 使用 `TrackSpec + append_track`。这不是测试环境跳过，而是已声明 optional 产品能力的运行时错误。

**文件：**
- 修改：`apps/api/xagent/domains/creative_studio/editor/video_editor.py`

- [x] 保留原有端到端导出测试作为失败复现。
- [x] 对 0.3 使用 `TrackSpec + append_track`，同时保留旧版 `add_track` 兼容分支。
- [x] 重跑真实导出测试，响应 200 且生成草稿成功。

### A8：cleanup evidence / gate lock 仍可能掩盖主错误

**实证：** 第三轮独立审查确认三个 gate 虽已分别捕获主要 teardown 异常，但 `cleanup-errors.json` 写入与 `FileStream.Dispose()` 仍处在未保护 finally 路径，异常时可能覆盖 `$primaryError`。

**文件：**
- 修改：`scripts/run_webapi_commercial_gate.ps1`
- 修改：`scripts/run_short_drama_commercial_gate.ps1`
- 修改：`scripts/run_rollback_drill.ps1`
- 修改：对应 release 合同测试。

- [x] 先扩展合同测试，要求 `Write-CleanupEvidence` 与 `Close-GateLock` 受保护 helper。
- [x] helper 内捕获异常、追加 cleanup error 并写 stderr，不从 finally 抛出。
- [x] 主流程结束后仍优先重抛原始 `$primaryError`；目标测试和五个 PowerShell parser 全部通过。

### A9：严格 file-write 超时时子 Agent 可无限挂起

**实证：** 完整后端回归稳定停在 `test_strict_real_loop_timeout_after_write_is_timeout`。任务栈显示 `asyncio.wait_for` 只发出一次取消，子任务仍保持 `Task cancelling` 并阻塞于 provider 的 `Event.wait`；第二次取消可使其终止。

**文件：**
- 修改：`apps/api/xagent/core/orchestration/parallel.py`

- [x] 保留 `asyncio.wait_for(..., timeout=task_timeout)` 的既有超时预算合同。
- [x] 用 `asyncio.shield` 避免 `wait_for` 在超时后无界等待子任务取消；随后以有界 grace period 重试取消。
- [x] 子任务在重试后仍不确认取消时 fail closed，不误报为普通 timeout。
- [x] 4 条超时 / 取消 / 预算定向用例和整个 `test_parallel_worktrees.py` 21 条用例通过；完整后端商用测试退出码为 0。

### A10：API 运行时镜像携带可修复 High 构建工具漏洞

**实证：** Docker Scout 因本机未登录无法扫描；固定 `aquasec/trivy:0.66.0` 及镜像 digest 后，API 镜像发现 `setuptools` 内置 `jaraco.context 5.3.0` 和 `wheel 0.45.1` 两类可修复 High，各在系统 Python 与 `/opt/venv` 重复；Web 镜像为 0。

**文件：**
- 修改：`apps/api/Dockerfile`
- 修改：`tests/release/test_container_contract.py`

- [x] 新增运行时不携带 `setuptools/wheel` 的合同测试，先稳定失败。
- [x] 在最终 runtime stage 从系统 Python 与应用 venv 卸载运行时不需要的 `setuptools/wheel`。
- [x] 重建 API 镜像，验证应用及系统 Python 均无 `setuptools/wheel`、`xagent` 可导入，并用同一 Trivy digest 复扫为 0 个可修复 High/Critical。
