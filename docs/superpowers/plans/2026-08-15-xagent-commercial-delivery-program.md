# X-Agent 商用交付整改总程序实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在同一 Git SHA 上关闭共享商用内核、Web/API、短剧、Tauri 桌面与回滚证据五个门，并只在全部本地证据通过时生成“本地商用候选”结论。

**架构：** 总程序只编排五份可独立验证的实施计划，不把一个组件的绿灯继承给另一个组件。远程推送、PR、标签、GitHub Release、签名、生产部署、付费供应商调用和客户生产验收继续保持独立授权，未授权时在清单中记录 `not_authorized`，不伪装成已完成。

**技术栈：** Python 3.11、FastAPI、React/Vite、Playwright、Docker Compose、Helm、Rust/Tauri 2、GitHub Actions、Postgres、Qdrant、Ollama

---

## 文件结构

- 创建：`docs/superpowers/plans/2026-08-15-xagent-commercial-kernel.md` —— 版本、Windows、密钥、安全扫描、依赖与镜像门。
- 创建：`docs/superpowers/plans/2026-08-15-xagent-webapi-delivery-gate.md` —— Web/API 整仓、隔离运行时、真实本地模型与无重试浏览器门。
- 创建：`docs/superpowers/plans/2026-08-15-xagent-short-drama-delivery-gate.md` —— 短剧默认离线产出、持久化、交付包与浏览器下载门。
- 创建：`docs/superpowers/plans/2026-08-15-xagent-desktop-delivery-gate.md` —— Tauri 安全代理、构建、安装、启动、连接和卸载门。
- 创建：`docs/superpowers/plans/2026-08-15-xagent-same-sha-evidence-rollback.md` —— 同一 SHA 清单、制品哈希、备份恢复与回滚门。
- 修改：`.github/workflows/ci.yml` —— 五门分别产出证据，最终聚合任务只验证同一 SHA。
- 创建：`scripts/commercial_delivery_gate.py` —— 校验五门清单及授权状态，不执行生产变更。
- 创建：`tests/release/test_commercial_delivery_gate.py` —— 防止缺门、SHA 漂移和未授权状态被误判为正式发布。

## 固定执行顺序

### 任务 1：建立执行基线

- [ ] **步骤 1：记录精确分支、SHA 与工作树状态**

运行：

```powershell
$repo = 'D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\commercial-delivery-20260815'
git -C $repo branch --show-current
git -C $repo rev-parse HEAD
git -C $repo status --porcelain=v1
```

预期：分支为 `codex/commercial-delivery-20260815`；状态仅包含已批准的计划文档；记录 SHA 为后续门的 `source_sha`。

- [ ] **步骤 2：验证规格与五份计划都存在**

运行：

```powershell
$repo = 'D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\commercial-delivery-20260815'
$required = @(
  'docs/superpowers/specs/2026-08-15-xagent-commercial-delivery-remediation-design.md',
  'docs/superpowers/plans/2026-08-15-xagent-commercial-kernel.md',
  'docs/superpowers/plans/2026-08-15-xagent-webapi-delivery-gate.md',
  'docs/superpowers/plans/2026-08-15-xagent-short-drama-delivery-gate.md',
  'docs/superpowers/plans/2026-08-15-xagent-desktop-delivery-gate.md',
  'docs/superpowers/plans/2026-08-15-xagent-same-sha-evidence-rollback.md'
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $repo $_)) }
if ($missing) { throw "Missing plan files: $($missing -join ', ')" }
```

预期：退出码 `0`，无缺失文件。

### 任务 2：按依赖顺序实施五门

- [ ] **步骤 1：执行共享商用内核计划**

执行：`docs/superpowers/plans/2026-08-15-xagent-commercial-kernel.md`

预期：版本、Windows 初始化、密钥、安全扫描、依赖和镜像测试全部通过；工作树中没有明文供应商密钥。

- [ ] **步骤 2：执行 Web/API 交付门计划**

执行：`docs/superpowers/plans/2026-08-15-xagent-webapi-delivery-gate.md`

预期：整仓后端、前端、SDK、Compose、迁移、真实本地 Ollama 和 Playwright 零重试同 SHA 通过。

- [ ] **步骤 3：执行短剧交付门计划**

执行：`docs/superpowers/plans/2026-08-15-xagent-short-drama-delivery-gate.md`

预期：默认配置无外网调用，短剧成功产出、持久化、可重新打开，并可下载校验过的 ZIP 交付包。

- [ ] **步骤 4：执行桌面交付门计划**

执行：`docs/superpowers/plans/2026-08-15-xagent-desktop-delivery-gate.md`

预期：Rust 质量门、MSI/NSIS 构建、安装后诊断、GUI 启动、后端连接和卸载通过；未签名状态明确记录。

- [ ] **步骤 5：执行同一 SHA 与回滚计划**

执行：`docs/superpowers/plans/2026-08-15-xagent-same-sha-evidence-rollback.md`

预期：五门证据、制品哈希、备份恢复和应用回滚都指向同一 `source_sha`，生成 `candidate_local` 清单。

### 任务 3：最终审计与交付边界

- [ ] **步骤 1：运行最终聚合门**

运行：

```powershell
$repo = 'D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\commercial-delivery-20260815'
$sha = git -C $repo rev-parse HEAD
python "$repo\scripts\commercial_delivery_gate.py" verify `
  --evidence-root "$repo\output\commercial-delivery\$sha" `
  --source-sha $sha `
  --require-clean
```

预期：输出 `commercial delivery candidate: candidate_local`；缺任一门、任一失败、SHA 不一致或工作树不干净时退出码必须为 `1`。

- [ ] **步骤 2：扫描泄密与计划偏离**

运行：

```powershell
$repo = 'D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\commercial-delivery-20260815'
git -C $repo diff --check
rg -n --hidden --glob '!.git/**' --glob '!output/**' '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)' $repo
```

预期：`git diff --check` 退出码 `0`；泄密扫描无匹配。若命中测试假值，先把测试假值改成不符合真实密钥格式的固定字符串。

- [ ] **步骤 3：确认授权状态没有越界**

读取：PowerShell 路径 `output/commercial-delivery/$sha/commercial-delivery-manifest.json`，其中 `$sha = (git rev-parse HEAD).Trim()`。

预期字段：

```json
{
  "classification": "candidate_local",
  "remote_release": "not_authorized",
  "production_deployment": "not_authorized",
  "paid_provider_acceptance": "not_authorized",
  "customer_production_acceptance": "not_authorized"
}
```

- [ ] **步骤 4：冻结最终本地候选 SHA**

```powershell
if (git status --porcelain) { throw 'all implementation commits must be complete before final evidence' }
git log -1 --format='%H %s'
```

预期：工作树为空并输出唯一最终 SHA；随后重新运行最终聚合门，使所有最终证据指向该 SHA。证据目录保持忽略，不进入 Git。

## 总程序完成判定

只有以下条件同时成立才可汇报“本地商用候选完成”：

1. 五份子计划全部打勾并有同一 SHA 的机器可读证据；
2. 三个产品门 `webapi`、`short_drama`、`desktop` 各自通过；
3. 密钥、依赖、镜像、安全扫描、备份恢复与回滚门通过；
4. 正式发布、生产部署、付费调用和客户生产验收仍按真实授权状态陈述；
5. 不使用历史 Release、旧截图、mock、单元测试或构建成功替代本轮端到端证据。
