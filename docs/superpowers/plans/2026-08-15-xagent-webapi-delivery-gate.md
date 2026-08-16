# X-Agent Web/API 商用交付门实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在同一 SHA 上完成后端整仓、前端、SDK、隔离 Compose、迁移、真实本地 Ollama 和零重试浏览器验收，并输出机器可读 Web/API 门证据。

**架构：** CI 的快速 Web/API scope 继续用于快速反馈，但不再代表商用门；商用门显式运行整仓 API 测试。浏览器门使用独立 Compose 项目和幂等 Git 工作区准备器，预热并实测本地 Ollama，Playwright 不自动重试，所有截图、下载与日志写入按 SHA 隔离的忽略目录。

**技术栈：** pytest、React/Vite、TypeScript、Node test、Docker Compose、Alembic、Ollama、Playwright/Chromium、PowerShell/Python

---

## 文件结构

- 创建：`scripts/run_backend_commercial_tests.py`、`tests/release/test_backend_commercial_runner.py` —— 不排除任何 API 产品测试的商用测试入口。
- 创建：`scripts/prepare_e2e_workspace.py`、`tests/release/test_prepare_e2e_workspace.py` —— 只在指定 Compose 项目卷内幂等创建验收 Git 仓库。
- 修改：`tests/e2e/playwright.config.ts` —— 商用门零重试、证据目录按环境变量配置。
- 修改：`tests/e2e/specs/webapi-r2-full-compose.spec.ts` —— 长任务显式超时、证据目录、下载与刷新恢复断言。
- 创建：`scripts/run_webapi_commercial_gate.ps1` —— 同一 SHA 顺序执行源码、构建、运行时、模型、浏览器门并写证据。
- 创建：`tests/release/test_webapi_gate_script.py` —— 脚本合同和授权边界。
- 修改：`.github/workflows/ci.yml` —— 新增整仓 API 与 Web/API 制品任务，保留真实模型为本地交付证据。
- 修改：`.gitignore` —— 忽略 `output/commercial-delivery/`，不再逐张维护截图忽略规则。

### 任务 1：建立无排除的后端整仓入口

**文件：**
- 创建：`scripts/run_backend_commercial_tests.py`
- 创建：`tests/release/test_backend_commercial_runner.py`

- [ ] **步骤 1：编写 runner 合同测试**

```python
from scripts import run_backend_commercial_tests as runner


def test_commercial_runner_has_no_exclusions() -> None:
    assert runner.pytest_args() == ["-ra", "-q", "tests"]


def test_commercial_runner_targets_api_root() -> None:
    assert runner.API_ROOT.name == "api"
    assert (runner.API_ROOT / "tests").is_dir()
```

- [ ] **步骤 2：运行测试确认模块不存在**

运行：`python -m pytest tests/release/test_backend_commercial_runner.py -q`

预期：FAIL，报错不能导入 `run_backend_commercial_tests`。

- [ ] **步骤 3：实现最小 runner**

```python
REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"


def pytest_args() -> list[str]:
    return ["-ra", "-q", "tests"]


def main() -> int:
    os.chdir(API_ROOT)
    sys.path.insert(0, str(API_ROOT))
    return pytest.main(pytest_args())
```

该入口不得导入 `EXCLUDED_TEST_MODULES`，也不得使用 `--ignore` 或 `--deselect`。

- [ ] **步骤 4：运行 runner 并保留完整失败清单**

运行：

```powershell
$env:PYTHONNOUSERSITE='1'
python scripts/run_backend_commercial_tests.py
```

预期：在短剧修复前可红灯，但必须完成到 pytest 汇总而非挂死；短剧计划完成后为零 failed。任何 `skipped` 项逐条分类为平台不适用或外部授权，不能静默计作验证通过。

- [ ] **步骤 5：提交整仓入口**

```bash
git add scripts/run_backend_commercial_tests.py tests/release/test_backend_commercial_runner.py
git commit -m "test: add full backend commercial gate"
```

### 任务 2：固定前端、SDK 与生产构建门

**文件：**
- 修改：`packages/sdk-ts/package-lock.json`
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：从锁文件全新安装并运行所有门**

运行：

```powershell
npm --prefix apps/web ci
npm --prefix apps/web run lint
npm --prefix apps/web run lint:release
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
npm --prefix packages/sdk-ts ci
npm --prefix packages/sdk-ts run test
npm --prefix packages/sdk-ts run typecheck
npm --prefix packages/sdk-ts run build
npm --prefix tests/e2e ci
```

预期：Web 单测 `43 passed` 或更多、lint/typecheck/build 全部退出码 `0`；SDK `5 passed` 或更多并生成 `dist`；E2E 依赖严格按 lock 安装。

- [ ] **步骤 2：验证制品内容而非只看退出码**

运行：

```powershell
$required = @(
  'apps/web/dist/index.html',
  'packages/sdk-ts/dist/index.js',
  'packages/sdk-ts/dist/index.d.ts'
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath $_) -or (Get-Item -LiteralPath $_).Length -eq 0 }
if ($missing) { throw "Missing build artifacts: $($missing -join ', ')" }
```

预期：退出码 `0`，三个制品存在且非空。

- [ ] **步骤 3：在 CI 分开命名快速门和商用门**

将现有后端 job 的名称标为 `Backend fast feedback (Web/API scope)`；新增 `backend-commercial` job，执行 `python scripts/run_backend_commercial_tests.py`。`release` job 必须依赖 `backend-commercial`、`frontend`、`supply-chain`，不再只依赖 narrow scope。

- [ ] **步骤 4：提交构建门**

```bash
git add packages/sdk-ts/package-lock.json .github/workflows/ci.yml
git commit -m "ci: separate full backend and Web build gates"
```

### 任务 3：幂等准备 Compose 验收工作区

**文件：**
- 创建：`scripts/prepare_e2e_workspace.py`
- 创建：`tests/release/test_prepare_e2e_workspace.py`

- [ ] **步骤 1：编写命令与安全边界测试**

```python
def test_commands_target_only_named_project_and_workspace() -> None:
    commands = workspace_commands(
        compose_file=Path("deploy/compose/docker-compose.yml"),
        project="xagent-commercial-a1b2c3d4",
    )
    assert commands[0][-5:] == ["api", "git", "-C", "/data/workspace", "init"]
    assert all("xagent-commercial-a1b2c3d4" in command for command in commands)
    assert all("/data/workspace" in command for command in commands)


def test_project_name_rejects_shell_metacharacters() -> None:
    with pytest.raises(ValueError, match="invalid compose project"):
        workspace_commands(Path("deploy/compose/docker-compose.yml"), "xagent;remove")
```

- [ ] **步骤 2：运行失败测试**

运行：`python -m pytest tests/release/test_prepare_e2e_workspace.py -q`

预期：FAIL，模块不存在。

- [ ] **步骤 3：实现固定参数 subprocess 调用**

```python
PROJECT_PATTERN = re.compile(r"^xagent-commercial-[a-f0-9]{8}$")


def compose_prefix(compose_file: Path, project: str) -> list[str]:
    if PROJECT_PATTERN.fullmatch(project) is None:
        raise ValueError("invalid compose project")
    return ["docker", "compose", "-p", project, "-f", str(compose_file)]


def workspace_commands(compose_file: Path, project: str) -> list[list[str]]:
    prefix = compose_prefix(compose_file, project) + ["exec", "-T", "api"]
    return [
        prefix + ["git", "-C", "/data/workspace", "init"],
        prefix + ["git", "-C", "/data/workspace", "config", "user.name", "X-Agent E2E"],
        prefix + ["git", "-C", "/data/workspace", "config", "user.email", "e2e@xagent.local"],
        prefix + ["git", "-C", "/data/workspace", "commit", "--allow-empty", "-m", "e2e baseline"],
    ]
```

执行前用 `docker compose -p $project -f deploy/compose/docker-compose.yml ps --services --filter status=running` 确认仅目标项目的 `api` 在运行。若仓库已有 HEAD，跳过 commit；不得删除、清空、移动或重置工作区内容。

- [ ] **步骤 4：验证单元和真实幂等性**

运行：

```powershell
python -m pytest tests/release/test_prepare_e2e_workspace.py -q
$sha8 = (git rev-parse --short=8 HEAD).Trim()
python scripts/prepare_e2e_workspace.py --compose-file deploy/compose/docker-compose.yml --project "xagent-commercial-$sha8"
python scripts/prepare_e2e_workspace.py --compose-file deploy/compose/docker-compose.yml --project "xagent-commercial-$sha8"
```

预期：测试 PASS；两次命令均退出码 `0`，第二次报告 `workspace already initialized`，已有 HEAD 未改变。

- [ ] **步骤 5：提交工作区准备器**

```bash
git add scripts/prepare_e2e_workspace.py tests/release/test_prepare_e2e_workspace.py
git commit -m "test: prepare isolated Git workspace for browser gate"
```

### 任务 4：让 Playwright 商用门零重试且证据按 SHA 隔离

**文件：**
- 修改：`tests/e2e/playwright.config.ts`
- 修改：`tests/e2e/specs/webapi-r2-full-compose.spec.ts`

- [ ] **步骤 1：先写配置合同测试**

在 `tests/release/test_webapi_gate_script.py` 添加：

```python
def test_playwright_commercial_config_disables_retries() -> None:
    text = (ROOT / "tests/e2e/playwright.config.ts").read_text(encoding="utf-8")
    assert "retries: 0" in text
    assert "E2E_EVIDENCE_DIR" in text
```

- [ ] **步骤 2：运行失败测试**

运行：`python -m pytest tests/release/test_webapi_gate_script.py -q`

预期：FAIL，现有配置包含 `retries: 1` 且没有证据目录变量。

- [ ] **步骤 3：修改 Playwright 配置**

```typescript
const evidenceDir = process.env.E2E_EVIDENCE_DIR || "../../output/e2e-local";

export default defineConfig({
  testDir: "./specs",
  outputDir: `${evidenceDir}/test-results`,
  timeout: 30_000,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: `${evidenceDir}/report` }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium", channel: "chrome" } }],
});
```

- [ ] **步骤 4：修正长任务和截图路径**

`webapi-r2-full-compose.spec.ts` 从 `process.env.E2E_EVIDENCE_DIR` 派生 `screenshotDir`。开发任务 test 设置 `test.setTimeout(660_000)`，请求 timeout 为 `600_000`；继续验证下载内容、补丁、commit 和 diff 四类产物，而不是只等待 HTTP 200。所有 `page.screenshot` 都写到该目录。

- [ ] **步骤 5：连续运行三轮零重试浏览器门**

运行：

```powershell
$sha = (git rev-parse HEAD).Trim()
$env:E2E_EVIDENCE_DIR = (Resolve-Path .).Path + "\output\commercial-delivery\$sha\webapi\browser"
$env:E2E_BASE_URL = 'http://127.0.0.1:3000'
1..3 | ForEach-Object {
  npm --prefix tests/e2e exec -- playwright test specs/webapi-r2-full-compose.spec.ts --reporter=list
  if ($LASTEXITCODE -ne 0) { throw "Playwright commercial run $_ failed" }
}
```

预期：每轮 `6 passed`、`0 flaky`、`0 retried`。任一轮失败，保存该轮 trace/log 并按 systematic-debugging 流程修复根因，然后从三轮第 1 轮重新计数。

- [ ] **步骤 6：提交浏览器门**

```bash
git add tests/e2e/playwright.config.ts tests/e2e/specs/webapi-r2-full-compose.spec.ts tests/release/test_webapi_gate_script.py
git commit -m "test: make Web API browser gate retry free"
```

### 任务 5：编排同一 SHA 的 Web/API 实际验收

**文件：**
- 创建：`scripts/run_webapi_commercial_gate.ps1`
- 修改：`tests/release/test_webapi_gate_script.py`
- 修改：`.gitignore`

- [ ] **步骤 1：扩充脚本合同测试**

```python
def test_gate_script_requires_real_ollama_and_same_sha() -> None:
    text = (ROOT / "scripts/run_webapi_commercial_gate.ps1").read_text(encoding="utf-8")
    for required in (
        "git rev-parse HEAD", "git status --porcelain", "docker compose",
        "alembic upgrade head", "prepare_e2e_workspace.py", "ollama",
        "webapi-r2-full-compose.spec.ts", "source_sha", "passed",
    ):
        assert required in text
    assert "MockLLM" not in text
```

- [ ] **步骤 2：运行测试确认脚本缺失**

运行：`python -m pytest tests/release/test_webapi_gate_script.py -q`

预期：FAIL，脚本不存在。

- [ ] **步骤 3：实现 fail-fast PowerShell 编排**

脚本参数固定为：

```powershell
param(
  [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$ComposeFile = 'deploy/compose/docker-compose.yml',
  [string]$OllamaModel = 'qwen3:4b'
)
$ErrorActionPreference = 'Stop'
$sourceSha = (git -C $RepoRoot rev-parse HEAD).Trim()
if (git -C $RepoRoot status --porcelain) { throw 'commercial gate requires a clean worktree' }
$project = "xagent-commercial-$($sourceSha.Substring(0, 8))"
$evidence = Join-Path $RepoRoot "output/commercial-delivery/$sourceSha/webapi"
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
```

随后顺序执行：版本门、`run_backend_commercial_tests.py`、Web/SDK ci/test/typecheck/build、Compose `up -d --build`、容器健康、`alembic upgrade head` 与 current=head、工作区准备器、本机 `ollama list` 确认精确模型、容器访问 `host.docker.internal:11434/api/tags`、Playwright 零重试套件。每一步非零立即退出；`finally` 收集 `docker compose ps` 和 `logs --no-color`，但不自动删除具名卷。

成功时使用 `ConvertTo-Json` 写入：

```json
{
  "gate": "webapi",
  "source_sha": "由脚本读取的四十位 Git SHA",
  "status": "passed",
  "real_local_model": "ollama/qwen3:4b",
  "playwright_retries": 0,
  "production_deployment": "not_authorized"
}
```

- [ ] **步骤 4：忽略运行证据并验证脚本静态合同**

在 `.gitignore` 添加 `output/commercial-delivery/`。运行：

```powershell
python -m pytest tests/release/test_webapi_gate_script.py -q
pwsh -NoProfile -Command '$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile("scripts/run_webapi_commercial_gate.ps1", [ref]$null, [ref]$errors) > $null; if ($errors) { $errors | Out-String | Write-Error }'
```

预期：测试 PASS，PowerShell 解析无错误。

- [ ] **步骤 5：提交编排器**

```bash
git add scripts/run_webapi_commercial_gate.ps1 tests/release/test_webapi_gate_script.py .gitignore
git commit -m "test: orchestrate same SHA Web API delivery gate"
```

### 任务 6：运行 Web/API 商用门并审计证据

- [ ] **步骤 1：从干净 SHA 运行一次完整门**

运行：`pwsh -NoProfile -File scripts/run_webapi_commercial_gate.ps1`

预期：退出码 `0`；`output/commercial-delivery/$sourceSha/webapi/gate.json` 为 `passed`；整仓 pytest、Compose 深健康、迁移、真实 Ollama、六项 Playwright 均在本轮日志中。

- [ ] **步骤 2：核对证据和工作树**

运行：

```powershell
$sha = (git rev-parse HEAD).Trim()
$gate = Get-Content -Raw -LiteralPath "output/commercial-delivery/$sha/webapi/gate.json" | ConvertFrom-Json
if ($gate.source_sha -ne $sha -or $gate.status -ne 'passed' -or $gate.playwright_retries -ne 0) { throw 'invalid webapi evidence' }
git status --porcelain
```

预期：证据与当前 SHA 相同且状态通过；工作树为空。此结果只证明本地 Web/API 商用候选，不证明远程发布或客户生产验收。

## 本计划完成判定

同一 SHA 的后端整仓、Web、SDK、Compose、迁移、真实本地 Ollama、浏览器六功能链路全部通过；Playwright 无 retry/flaky；下载产物能打开；证据 JSON 与日志写在该 SHA 的忽略目录；未授权外部状态明确为 `not_authorized`。
