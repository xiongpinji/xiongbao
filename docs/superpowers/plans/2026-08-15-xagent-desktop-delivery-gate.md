# X-Agent Tauri 桌面商用交付门实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 生成可审计的 Windows MSI/NSIS 制品，在隔离本地目录实际完成诊断连接、安装、首次启动、关闭、重启与卸载，并将未签名状态准确标为 `unsigned_local_candidate`。

**架构：** Rust 层集中校验后端 URL、路径和 HTTP 方法，桌面后端只允许 loopback。安装后的同一可执行文件支持 `--diagnostics-file` 无界面健康诊断，安装门用它证明打包二进制能连接本轮 Web/API；GUI 进程生命周期另行验证。制品收集器记录 SHA-256、大小、架构、版本、构建 SHA 和签名状态。

**技术栈：** Rust 2021、Tauri 2、reqwest、Tokio、Cargo、Windows MSI/NSIS、PowerShell、GitHub Actions Windows runner

---

## 文件结构

- 修改：`apps/desktop/src/lib.rs` —— loopback URL/path/method 验证、健康诊断与单元测试。
- 修改：`apps/desktop/src/main.rs` —— `--diagnostics-file` 命令行入口和 GUI 入口分流。
- 修改：`apps/desktop/Cargo.toml`、`apps/desktop/Cargo.lock` —— URL/错误依赖与产品版本锁定。
- 修改：`apps/desktop/tauri.conf.json` —— 产品版本、固定 installer targets 与安全配置。
- 创建：`scripts/collect_desktop_artifacts.py`、`tests/release/test_collect_desktop_artifacts.py` —— 制品摘要和签名分类。
- 创建：`scripts/verify_desktop_installer.ps1`、`tests/release/test_desktop_installer_script.py` —— 安全安装、诊断、GUI 生命周期和卸载。
- 创建：`scripts/run_desktop_commercial_gate.ps1`、`tests/release/test_desktop_gate_script.py` —— Rust/build/installer 同 SHA 门。
- 修改：`.github/workflows/ci.yml` —— `windows-latest` 桌面质量与 bundle job。

### 任务 1：锁定桌面后端代理边界

**文件：**
- 修改：`apps/desktop/src/lib.rs`
- 修改：`apps/desktop/Cargo.toml`
- 修改：`apps/desktop/Cargo.lock`

- [ ] **步骤 1：先写 URL、路径和方法单元测试**

在 `apps/desktop/src/lib.rs` 底部添加：

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backend_url_accepts_loopback_api_path() {
        let url = build_backend_url("http://127.0.0.1:8000", "/api/v1/system/capabilities").unwrap();
        assert_eq!(url.as_str(), "http://127.0.0.1:8000/api/v1/system/capabilities");
    }

    #[test]
    fn backend_url_rejects_remote_hosts_and_path_escape() {
        assert!(build_backend_url("https://example.com", "/health").is_err());
        assert!(build_backend_url("http://127.0.0.1:8000", "//example.com/steal").is_err());
        assert!(build_backend_url("http://127.0.0.1:8000", "/api/v1/../admin").is_err());
        assert!(build_backend_url("http://127.0.0.1:8000", "health").is_err());
    }

    #[test]
    fn request_method_is_allowlisted() {
        assert_eq!(parse_method("get").unwrap(), reqwest::Method::GET);
        assert_eq!(parse_method("DELETE").unwrap(), reqwest::Method::DELETE);
        assert!(parse_method("CONNECT").is_err());
        assert!(parse_method("TRACE").is_err());
    }
}
```

- [ ] **步骤 2：运行测试确认函数不存在**

运行：`cargo test --manifest-path apps/desktop/Cargo.toml --locked`

预期：FAIL，找不到 `build_backend_url` 和 `parse_method`。

- [ ] **步骤 3：实现 loopback URL 和 allowlist**

在 `Cargo.toml` 添加 `url = "2"`，实现：

```rust
fn parse_method(method: &str) -> Result<reqwest::Method, String> {
    match method.to_ascii_uppercase().as_str() {
        "GET" => Ok(reqwest::Method::GET),
        "POST" => Ok(reqwest::Method::POST),
        "PUT" => Ok(reqwest::Method::PUT),
        "PATCH" => Ok(reqwest::Method::PATCH),
        "DELETE" => Ok(reqwest::Method::DELETE),
        _ => Err(format!("unsupported method: {method}")),
    }
}


fn build_backend_url(base: &str, path: &str) -> Result<url::Url, String> {
    if !path.starts_with('/') || path.starts_with("//") || path.split('/').any(|part| part == "..") {
        return Err("backend path must be an absolute non-escaping path".to_string());
    }
    let mut base_url = url::Url::parse(base).map_err(|error| error.to_string())?;
    let host = base_url.host_str().unwrap_or_default();
    if base_url.scheme() != "http" || !matches!(host, "127.0.0.1" | "localhost" | "::1") {
        return Err("backend base URL must use HTTP loopback".to_string());
    }
    base_url.set_path(path);
    base_url.set_query(None);
    base_url.set_fragment(None);
    Ok(base_url)
}
```

`call_backend_api` 从 `XAGENT_DESKTOP_API_URL` 读取 base，缺省 `http://127.0.0.1:8000`；使用 `client.request(parse_method(&method)?, build_backend_url(&base, &path)?)`。错误不得包含 bearer token 或请求 body。

- [ ] **步骤 4：运行 Rust 质量门**

运行：

```powershell
cargo fmt --manifest-path apps/desktop/Cargo.toml -- --check
cargo clippy --manifest-path apps/desktop/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path apps/desktop/Cargo.toml --locked
```

预期：全部退出码 `0`。

- [ ] **步骤 5：提交代理边界**

```bash
git add apps/desktop/src/lib.rs apps/desktop/Cargo.toml apps/desktop/Cargo.lock
git commit -m "fix: constrain desktop backend proxy to loopback"
```

### 任务 2：为安装后可执行文件增加健康诊断

**文件：**
- 修改：`apps/desktop/src/lib.rs`
- 修改：`apps/desktop/src/main.rs`

- [ ] **步骤 1：编写诊断结果单元测试**

```rust
#[tokio::test]
async fn diagnostics_reports_backend_health() {
    let server = mockito::Server::new_async().await;
    let mock = server.mock("GET", "/health")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"status":"ok","version":"1.1.3"}"#)
        .create_async().await;
    let result = diagnose_backend(&server.url()).await.unwrap();
    assert_eq!(result["status"], "ok");
    assert_eq!(result["version"], "1.1.3");
    mock.assert_async().await;
}
```

在 `[dev-dependencies]` 添加 `mockito = "1"`。

- [ ] **步骤 2：运行测试确认诊断函数不存在**

运行：`cargo test --manifest-path apps/desktop/Cargo.toml --locked diagnostics_reports_backend_health`

预期：FAIL，找不到 `diagnose_backend`。

- [ ] **步骤 3：实现诊断与文件输出入口**

```rust
pub async fn diagnose_backend(base: &str) -> Result<serde_json::Value, String> {
    let url = build_backend_url(base, "/health")?;
    let response = reqwest::Client::new().get(url).send().await.map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("backend health returned {}", response.status()));
    }
    response.json::<serde_json::Value>().await.map_err(|error| error.to_string())
}
```

`main.rs` 解析精确参数对 `--diagnostics-file C:\XAgentEvidence\desktop-diagnostics.json`；实际参数路径不是绝对路径或父目录不存在时退出 `2`。诊断成功写：

```json
{
  "desktop_version": "1.1.3",
  "backend_url": "http://127.0.0.1:8000",
  "backend_status": "ok",
  "backend_version": "1.1.3"
}
```

失败写同一 schema 的 `backend_status: "failed"` 和不含 secret 的 `error`，退出 `1`。未传该参数时才调用 `xagent_desktop_lib::run()`。

- [ ] **步骤 4：验证诊断二进制**

运行：

```powershell
cargo test --manifest-path apps/desktop/Cargo.toml --locked
cargo build --manifest-path apps/desktop/Cargo.toml --release --locked
$diagnostics = (Resolve-Path .).Path + '\output\desktop-diagnostics.json'
New-Item -ItemType Directory -Force -Path (Split-Path $diagnostics) | Out-Null
& '.\apps\desktop\target\release\xagent-desktop.exe' --diagnostics-file $diagnostics
Get-Content -Raw -LiteralPath $diagnostics | ConvertFrom-Json
```

预期：在本地 API `1.1.3` 健康时进程退出 `0`，JSON 四个字段匹配；API 不可达时退出 `1` 且不会启动 GUI。

- [ ] **步骤 5：提交诊断入口**

```bash
git add apps/desktop/src/lib.rs apps/desktop/src/main.rs apps/desktop/Cargo.toml apps/desktop/Cargo.lock
git commit -m "feat: add installed desktop backend diagnostics"
```

### 任务 3：收集安装制品摘要与签名状态

**文件：**
- 创建：`scripts/collect_desktop_artifacts.py`
- 创建：`tests/release/test_collect_desktop_artifacts.py`

- [ ] **步骤 1：编写制品清单测试**

```python
def test_collect_records_hash_size_arch_and_unsigned_state(tmp_path: Path) -> None:
    nsis = tmp_path / "X-Agent_1.1.3_x64-setup.exe"
    msi = tmp_path / "X-Agent_1.1.3_x64_en-US.msi"
    nsis.write_bytes(b"nsis")
    msi.write_bytes(b"msi")
    manifest = collect_artifacts(tmp_path, source_sha="a" * 40, version="1.1.3")
    assert manifest["classification"] == "unsigned_local_candidate"
    assert {item["format"] for item in manifest["artifacts"]} == {"nsis", "msi"}
    assert all(item["arch"] == "x64" for item in manifest["artifacts"])
    assert all(len(item["sha256"]) == 64 and item["size_bytes"] > 0 for item in manifest["artifacts"])
```

- [ ] **步骤 2：运行测试确认模块缺失**

运行：`python -m pytest tests/release/test_collect_desktop_artifacts.py -q`

预期：FAIL，收集器不存在。

- [ ] **步骤 3：实现严格收集器**

`collect_artifacts(bundle_root, source_sha, version)` 只接受 40 位小写十六进制 SHA，递归收集恰好一个 `.msi` 和一个 `-setup.exe`，文件名必须包含精确版本和 `x64`。每个条目包含：

```python
{
    "path": artifact.relative_to(bundle_root).as_posix(),
    "format": "msi" if artifact.suffix.lower() == ".msi" else "nsis",
    "version": version,
    "arch": "x64",
    "size_bytes": artifact.stat().st_size,
    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    "signature": "unsigned",
}
```

缺件、多件、空文件、版本不符或 `signtool verify /pa` 意外报告签名无效都退出 `1`。本计划不生成自签名证书，不把自签名包标为正式签名。

- [ ] **步骤 4：运行测试**

运行：`python -m pytest tests/release/test_collect_desktop_artifacts.py -q`

预期：PASS。

- [ ] **步骤 5：提交收集器**

```bash
git add scripts/collect_desktop_artifacts.py tests/release/test_collect_desktop_artifacts.py
git commit -m "feat: inventory desktop installer artifacts"
```

### 任务 4：构建 Windows MSI 与 NSIS

**文件：**
- 修改：`apps/desktop/tauri.conf.json`
- 修改：`apps/desktop/Cargo.lock`

- [ ] **步骤 1：验证版本和 Tauri 配置**

运行：

```powershell
python scripts/verify_release_versions.py --tag v1.1.3
npm --prefix apps/web ci
npm --prefix apps/web run build
cargo install tauri-cli --version '^2' --locked
Push-Location apps/desktop
cargo tauri info
Pop-Location
```

预期：产品版本一致；Tauri 识别 Windows x86_64、WebView2、MSI 与 NSIS。

- [ ] **步骤 2：构建 locked installers**

运行：

```powershell
cargo fmt --manifest-path apps/desktop/Cargo.toml -- --check
cargo clippy --manifest-path apps/desktop/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path apps/desktop/Cargo.toml --locked
Push-Location apps/desktop
cargo tauri build --bundles msi,nsis
Pop-Location
```

预期：退出码 `0`；`apps/desktop/target/release/bundle/msi` 和 `nsis` 各有一个非空 1.1.3 x64 installer；`git status --porcelain` 不含未解释 schema 或 lock 漂移。

- [ ] **步骤 3：收集摘要**

运行：

```powershell
$sha = (git rev-parse HEAD).Trim()
python scripts/collect_desktop_artifacts.py `
  --bundle-root apps/desktop/target/release/bundle `
  --source-sha $sha `
  --version 1.1.3 `
  --output "output/commercial-delivery/$sha/desktop/artifacts.json"
```

预期：输出 classification 为 `unsigned_local_candidate`，MSI/NSIS 各一个且摘要可重新计算。

- [ ] **步骤 4：提交配置/锁文件**

```bash
git add apps/desktop/tauri.conf.json apps/desktop/Cargo.lock
git commit -m "build: produce versioned Windows desktop installers"
```

### 任务 5：安全验证安装、连接、启动、重启和卸载

**文件：**
- 创建：`scripts/verify_desktop_installer.ps1`
- 创建：`tests/release/test_desktop_installer_script.py`

- [ ] **步骤 1：编写 Windows 安全合同测试**

```python
def test_installer_script_scopes_all_mutation_to_test_root() -> None:
    text = (ROOT / "scripts/verify_desktop_installer.ps1").read_text(encoding="utf-8")
    assert "$env:LOCALAPPDATA" in text
    assert "XAgentCommercialTest" in text
    assert "-WindowStyle Hidden" in text
    assert "--diagnostics-file" in text
    assert "Get-Process | Stop-Process" not in text
    assert "Remove-Item -Recurse" not in text
    assert "production" not in text.lower()
```

- [ ] **步骤 2：运行测试确认脚本不存在**

运行：`python -m pytest tests/release/test_desktop_installer_script.py -q`

预期：FAIL，脚本不存在。

- [ ] **步骤 3：实现显式目标和 PID 级清理**

脚本参数：

```powershell
param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
  [string]$ApiUrl = 'http://127.0.0.1:8000'
)
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$testBase = Join-Path $env:LOCALAPPDATA "XAgentCommercialTest\$SourceSha"
$testRoot = [System.IO.Path]::GetFullPath($testBase)
$allowedBase = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'XAgentCommercialTest'))
if (-not $testRoot.StartsWith($allowedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw 'resolved test install root escaped allowlist'
}
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
```

仅接受 `apps/desktop/target/release/bundle/nsis` 下的精确 `-setup.exe`。使用 `Start-Process -WindowStyle Hidden -Wait -PassThru -ArgumentList @('/S', "/D=$testRoot")` 安装。精确解析 `$testRoot\X-Agent.exe`，以 `XAGENT_DESKTOP_API_URL=$ApiUrl` 启动 `--diagnostics-file` 并要求 JSON backend status/version 通过。随后启动 GUI 两次，每次只保存返回的 PID，等待窗口进程存活 10 秒后按该 PID `CloseMainWindow()`，超时才 `Stop-Process -Id $pid`。最后从 `$testRoot` 内精确解析 uninstaller，静默卸载并验证 exe 消失；不递归删除其他目录。

- [ ] **步骤 4：解析并静态验证脚本**

运行：

```powershell
python -m pytest tests/release/test_desktop_installer_script.py -q
pwsh -NoProfile -Command '$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile("scripts/verify_desktop_installer.ps1", [ref]$null, [ref]$errors) > $null; if ($errors) { $errors | Out-String | Write-Error }'
```

预期：测试 PASS，PowerShell 无语法错误。

- [ ] **步骤 5：在隔离目录实际运行 NSIS 验证**

运行：

```powershell
$sha = (git rev-parse HEAD).Trim()
$installers = @(Get-ChildItem -LiteralPath 'apps/desktop/target/release/bundle/nsis' -Filter '*-setup.exe' -File -Recurse)
if ($installers.Count -ne 1) { throw "Expected exactly one NSIS installer, found $($installers.Count)" }
$installer = $installers[0].FullName
pwsh -NoProfile -File scripts/verify_desktop_installer.ps1 -Installer $installer -SourceSha $sha
```

预期：安装、诊断、首次 GUI、关闭、重启、卸载全部 PASS；证据 JSON 记录精确 PID/路径/退出码且不含 token。用 computer-use 技能打开一次安装后的 GUI，确认标题为 `X-Agent`、Web 内容渲染且能访问本地 API，再按应用内关闭；截图写到该 SHA 的 desktop evidence 目录。

- [ ] **步骤 6：提交 installer verifier**

```bash
git add scripts/verify_desktop_installer.ps1 tests/release/test_desktop_installer_script.py
git commit -m "test: verify Windows desktop installer lifecycle"
```

### 任务 6：接入桌面独立门和 Windows CI

**文件：**
- 创建：`scripts/run_desktop_commercial_gate.ps1`
- 创建：`tests/release/test_desktop_gate_script.py`
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：编写门脚本合同**

```python
def test_desktop_gate_requires_quality_build_install_and_uninstall() -> None:
    text = (ROOT / "scripts/run_desktop_commercial_gate.ps1").read_text(encoding="utf-8")
    for required in (
        "cargo fmt", "cargo clippy", "cargo test", "cargo audit",
        "cargo tauri build", "collect_desktop_artifacts.py",
        "verify_desktop_installer.ps1", "unsigned_local_candidate", "source_sha",
    ):
        assert required in text
```

- [ ] **步骤 2：实现 fail-fast 桌面门**

脚本要求 Windows、干净工作树和健康本地 API 1.1.3，顺序执行 Rust 质量、`cargo audit --file apps/desktop/Cargo.lock`、Web build、Tauri build、artifact collect 和 NSIS lifecycle。成功写：

```json
{
  "gate": "desktop",
  "source_sha": "由脚本读取的四十位 Git SHA",
  "status": "passed",
  "classification": "unsigned_local_candidate",
  "installer_formats": ["msi", "nsis"],
  "install_lifecycle": "passed",
  "backend_connection": "passed",
  "code_signing": "not_authorized"
}
```

- [ ] **步骤 3：新增 Windows CI job**

`desktop` job 使用 `windows-latest`，安装 Node/Rust/Tauri prerequisites，执行 fmt/clippy/test/audit、Web build、`cargo tauri build --bundles msi,nsis`、artifact collect，并上传 installers 与 `artifacts.json`。CI 没有交互桌面和本地客户 API时，`install_lifecycle` 证据仍由本轮本地 Windows 商用门提供，CI 不伪造该字段。

- [ ] **步骤 4：验证并提交**

运行：

```powershell
python -m pytest tests/release/test_desktop_gate_script.py -q
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8')); print('ci yaml ok')"
```

预期：PASS。

```bash
git add scripts/run_desktop_commercial_gate.ps1 tests/release/test_desktop_gate_script.py .github/workflows/ci.yml
git commit -m "ci: add independent Tauri desktop delivery gate"
```

- [ ] **步骤 5：运行桌面商用门**

运行：`pwsh -NoProfile -File scripts/run_desktop_commercial_gate.ps1`

预期：同一 SHA 的 Rust、installer、diagnostics、GUI lifecycle 和 uninstall 通过，`gate.json` classification 严格为 `unsigned_local_candidate`。没有正式代码签名证书、时间戳服务和签名安装复核时，不得称为正式桌面商用发布。

## 本计划完成判定

fmt/clippy/test/locked build/audit 全绿；MSI/NSIS 真实生成且摘要一致；安装后同一二进制连接本地 Web/API；首次启动、关闭、重启、卸载均实际执行；GUI 有本轮可视证据；版本/SHA 一致；签名缺口准确阻断正式发布但不阻断 `unsigned_local_candidate` 本地候选。
