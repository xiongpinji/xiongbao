# X-Agent 共享商用内核实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 关闭版本漂移、Windows 初始化、明文密钥、安全扫描假绿、依赖漂移和不安全运行镜像六个 P0 门。

**架构：** API `pyproject.toml` 是产品版本唯一来源，验证器静态读取各运行时清单。LLM 覆盖文件只保存非密字段和 `SECRETREF:`，原始密钥只在当前进程内生效；安全扫描改为结构化、缺检查即失败。生产镜像由锁文件构建为非 root 最小运行层，Helm 支持不可变 digest。

**技术栈：** Python 3.11、pytest、FastAPI/Pydantic、Win32 Unicode API、httpx、Docker、Helm、GitHub Actions、npm、Cargo

---

## 文件结构

- 创建：`tests/release/test_release_version_gate.py` —— 版本漂移回归测试。
- 修改：`scripts/verify_release_versions.py` —— 静态读取 API、Web、Python runtime、Helm、Tauri 与 README 版本。
- 修改：`apps/api/xagent/__init__.py`、`deploy/helm/Chart.yaml`、`apps/desktop/Cargo.toml`、`apps/desktop/tauri.conf.json` —— 对齐产品版本 `1.1.3`。
- 修改：`scripts/r2_preflight.py`、`tests/release/test_r2_preflight.py` —— Windows Unicode 身份获取与安全回退。
- 创建：`apps/api/xagent/infra/secure_json.py`、`apps/api/tests/test_secure_json.py` —— 原子、私有 JSON 写入。
- 修改：`apps/api/xagent/api/v1/system.py` —— 非密字段/密钥引用持久化，原始密钥 session-only。
- 创建：`apps/api/tests/test_llm_config_security.py` —— 明文拒绝、引用解析、重启语义和 fail-closed 测试。
- 创建：`scripts/migrate_llm_overrides.py`、`tests/release/test_migrate_llm_overrides.py` —— 历史明文清理工具。
- 修改：`tests/security/scan.py`、创建 `tests/security/test_scan.py` —— 所有检查可计数、可注入、失败闭合。
- 创建：`apps/api/requirements.lock`、`packages/sdk-ts/package-lock.json` —— 可复现依赖。
- 修改：`apps/api/Dockerfile`、`deploy/helm/values.yaml`、`deploy/helm/templates/*.yaml` —— 多阶段非 root 镜像和 digest。
- 创建：`tests/release/test_container_contract.py`、`tests/release/test_helm_image_contract.py` —— 静态制品合同。
- 修改：`.github/workflows/ci.yml` —— 锁文件、安全审计、SBOM、Cargo audit 与内核门。

### 任务 1：扩大版本一致性门

**文件：**
- 创建：`tests/release/test_release_version_gate.py`
- 修改：`scripts/verify_release_versions.py`
- 修改：`apps/api/xagent/__init__.py`
- 修改：`deploy/helm/Chart.yaml`
- 修改：`apps/desktop/Cargo.toml`
- 修改：`apps/desktop/tauri.conf.json`

- [ ] **步骤 1：编写版本漂移失败测试**

```python
from pathlib import Path

from scripts.verify_release_versions import verify_versions


ROOT = Path(__file__).resolve().parents[2]


def test_current_tree_has_one_product_version() -> None:
    assert verify_versions(ROOT, tag="v1.1.3") == []


def test_runtime_drift_is_rejected(tmp_path: Path) -> None:
    for source in (
        "apps/api/pyproject.toml",
        "apps/web/package.json",
        "apps/api/xagent/__init__.py",
        "deploy/helm/Chart.yaml",
        "apps/desktop/Cargo.toml",
        "apps/desktop/tauri.conf.json",
        "README.md",
    ):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    runtime = tmp_path / "apps/api/xagent/__init__.py"
    runtime.write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    assert verify_versions(tmp_path) == [
        "Python runtime version 9.9.9 != API version 1.1.3"
    ]
```

- [ ] **步骤 2：运行测试确认现有门漏检且当前树漂移**

运行：`python -m pytest tests/release/test_release_version_gate.py -q`

预期：FAIL；当前树测试报告 Python runtime、Helm 或 Tauri 版本不一致，漂移测试因验证器未检查 runtime 而失败。

- [ ] **步骤 3：实现静态版本读取并对齐清单**

在 `scripts/verify_release_versions.py` 添加并由 `verify_versions()` 调用：

```python
def _read_assignment(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    raise ValueError(f"{name} string assignment not found")


def _read_yaml_scalar(path: Path, name: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == name:
            return value.strip().strip('"').strip("'")
    raise ValueError(f"{name} scalar not found")
```

静态读取 `apps/api/xagent/__init__.py::__version__`、`deploy/helm/Chart.yaml::{version,appVersion}`、`apps/desktop/Cargo.toml::package.version` 和 `apps/desktop/tauri.conf.json::version`，逐项与 API 版本比较。将四个漂移文件改为 `1.1.3`；TS SDK 保持独立版本 `0.1.0`，不纳入产品版本等值门。

- [ ] **步骤 4：验证版本门**

运行：

```powershell
python -m pytest tests/release/test_release_version_gate.py -q
python scripts/verify_release_versions.py --tag v1.1.3
```

预期：全部 PASS；脚本输出 `Web/API release versions match tag v1.1.3`。

- [ ] **步骤 5：提交版本门**

```bash
git add tests/release/test_release_version_gate.py scripts/verify_release_versions.py apps/api/xagent/__init__.py deploy/helm/Chart.yaml apps/desktop/Cargo.toml apps/desktop/tauri.conf.json
git commit -m "fix: enforce product version consistency"
```

### 任务 2：修复 Windows Unicode 初始化

**文件：**
- 修改：`tests/release/test_r2_preflight.py`
- 修改：`scripts/r2_preflight.py`

- [ ] **步骤 1：添加 Unicode API 与回退测试**

```python
@mock.patch("scripts.r2_preflight._get_windows_identity_unicode", return_value="DOMAIN\\熊宝")
def test_get_windows_identity_uses_unicode_api(unicode_identity: mock.Mock) -> None:
    assert r2_preflight.get_windows_identity(Path("C:/Windows/System32")) == "DOMAIN\\熊宝"
    unicode_identity.assert_called_once_with()


@mock.patch("scripts.r2_preflight._get_windows_identity_unicode", side_effect=OSError("unavailable"))
@mock.patch("scripts.r2_preflight.subprocess.run")
def test_get_windows_identity_fallback_decodes_utf8(run: mock.Mock, _unicode: mock.Mock) -> None:
    run.return_value = subprocess.CompletedProcess([], 0, "机器\\用户".encode("utf-8"), b"")
    assert r2_preflight.get_windows_identity(Path("C:/Windows/System32")) == "机器\\用户"
```

- [ ] **步骤 2：运行失败测试**

运行：`python -m pytest tests/release/test_r2_preflight.py -q`

预期：FAIL，报告 `_get_windows_identity_unicode` 不存在，原先三项 Windows 初始化错误仍可复现。

- [ ] **步骤 3：实现 Win32 Unicode 主路径和无损回退**

```python
def _get_windows_identity_unicode() -> str:
    import ctypes
    from ctypes import wintypes

    name_sam_compatible = 2
    size = wintypes.ULONG(0)
    secur32 = ctypes.WinDLL("secur32", use_last_error=True)
    function = secur32.GetUserNameExW
    function.argtypes = [wintypes.ULONG, wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG)]
    function.restype = wintypes.BOOL
    function(name_sam_compatible, None, ctypes.byref(size))
    if size.value == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(size.value)
    if not function(name_sam_compatible, buffer, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value.strip()


def _decode_identity(raw: bytes) -> str:
    for encoding in ("utf-8", _console_codepage()):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="surrogateescape").strip()
```

`get_windows_identity()` 先返回 `_get_windows_identity_unicode()`；仅在 `OSError` 时执行 `whoami.exe` 并交给 `_decode_identity()`。保留现有可执行文件路径验证和非零退出码处理。

- [ ] **步骤 4：验证 Windows 初始化全绿**

运行：

```powershell
python -m pytest tests/release/test_r2_preflight.py -q
python scripts/r2_preflight.py init-env --output output/r2-runtime/test.env --force
```

预期：测试 `21 passed`；命令退出码 `0`，生成文件不含解码异常且 ACL 检查通过。删除测试生成的 `output/r2-runtime/test.env`。

- [ ] **步骤 5：提交 Windows 修复**

```bash
git add scripts/r2_preflight.py tests/release/test_r2_preflight.py
git commit -m "fix: initialize Windows environment with Unicode identity"
```

### 任务 3：建立安全 JSON 原子写入

**文件：**
- 创建：`apps/api/xagent/infra/secure_json.py`
- 创建：`apps/api/tests/test_secure_json.py`

- [ ] **步骤 1：编写失败测试**

```python
import json
import os
from pathlib import Path

from xagent.infra.secure_json import write_private_json


def test_write_private_json_is_atomic_and_private(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "config.json"
    write_private_json(target, {"model": "ollama/qwen3:4b"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"model": "ollama/qwen3:4b"}
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600
```

- [ ] **步骤 2：运行测试验证模块缺失**

运行：`python -m pytest apps/api/tests/test_secure_json.py -q`

预期：FAIL，报错 `ModuleNotFoundError: xagent.infra.secure_json`。

- [ ] **步骤 3：实现最小原子写入函数**

```python
def write_private_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
```

在 Windows 上追加 `_restrict_windows_file(path)`，调用 `subprocess.run(["icacls.exe", str(path), "/inheritance:r", "/grant:r", f"{identity}:(R,W)"], check=True, capture_output=True)`；身份获取使用本任务 2 的 Unicode 原则，不读取或打印 JSON 内容。

- [ ] **步骤 4：运行测试**

运行：`python -m pytest apps/api/tests/test_secure_json.py -q`

预期：PASS；Windows 上额外断言目标 ACL 不包含 `Everyone` 或 `BUILTIN\\Users` 的写权限。

- [ ] **步骤 5：提交安全写入器**

```bash
git add apps/api/xagent/infra/secure_json.py apps/api/tests/test_secure_json.py
git commit -m "feat: write private configuration atomically"
```

### 任务 4：禁止 LLM 原始密钥落盘

**文件：**
- 创建：`apps/api/tests/test_llm_config_security.py`
- 修改：`apps/api/xagent/api/v1/system.py`
- 修改：`apps/api/tests/test_api_v1_honesty.py`

- [ ] **步骤 1：编写密钥持久化合同测试**

```python
def test_raw_key_is_session_only_and_never_written(client, monkeypatch, tmp_path):
    target = tmp_path / "llm_config_overrides.json"
    monkeypatch.setattr(system, "_LLM_OVERRIDES_PATH", target)
    response = client.put(
        "/api/v1/system/llm-config",
        headers=manage_headers(),
        json={"openai_api_key": "test-session-secret", "default_model": "gpt-4o-mini"},
    )
    assert response.status_code == 200
    assert response.json()["secret_persistence"] == "session_only"
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert "openai_api_key" not in saved
    assert "test-session-secret" not in target.read_text(encoding="utf-8")


def test_secret_ref_is_persisted_but_resolved_value_is_not(client, monkeypatch, tmp_path):
    target = tmp_path / "llm_config_overrides.json"
    monkeypatch.setattr(system, "_LLM_OVERRIDES_PATH", target)
    monkeypatch.setenv("XAGENT_TEST_OPENAI_KEY", "resolved-test-secret")
    response = client.put(
        "/api/v1/system/llm-config",
        headers=manage_headers(),
        json={"openai_api_key": "SECRETREF:env:XAGENT_TEST_OPENAI_KEY"},
    )
    assert response.status_code == 200
    assert json.loads(target.read_text(encoding="utf-8"))["openai_api_key"] == "SECRETREF:env:XAGENT_TEST_OPENAI_KEY"
    assert "resolved-test-secret" not in target.read_text(encoding="utf-8")
```

再添加两个直接函数测试：full 模式加载历史明文敏感字段抛 `RuntimeError`；lite 模式忽略该字段并记录 warning。

- [ ] **步骤 2：运行测试确认明文仍会写入**

运行：`python -m pytest apps/api/tests/test_llm_config_security.py apps/api/tests/test_api_v1_honesty.py -q`

预期：FAIL；断言显示 `openai_api_key` 仍存在于覆盖文件。

- [ ] **步骤 3：拆分敏感字段和持久字段**

```python
_LLM_SENSITIVE_FIELDS = frozenset({
    "proxy_api_key", "openai_api_key", "anthropic_api_key", "deepseek_api_key",
})
_LLM_PERSISTED_FIELDS = frozenset(_LLM_OVERRIDABLE_FIELDS) - _LLM_SENSITIVE_FIELDS


def _persistable_llm_changes(changed: dict[str, object]) -> dict[str, object]:
    persisted: dict[str, object] = {}
    for key, value in changed.items():
        if key in _LLM_PERSISTED_FIELDS:
            persisted[key] = value
        elif key in _LLM_SENSITIVE_FIELDS and is_secret_ref(value):
            persisted[key] = value
    return persisted
```

`_load_llm_overrides(mode: RunMode)` 只接受白名单。敏感值若为 `SECRETREF:`，通过 `resolve_secret(value, field=f"llm.{key}", lite=mode is RunMode.lite)` 应用，磁盘仍保留引用；敏感值若为原始字符串，full/enterprise 抛不含值的 `RuntimeError`，lite 记录字段名并丢弃。`_save_llm_overrides()` 改用 `write_private_json()`。

PUT 的运行时 `changed` 继续应用于当前进程；写盘仅合并 `_persistable_llm_changes(changed)`。响应增加：

```python
{
    "persisted": True,
    "persisted_fields": sorted(persistable_changes),
    "session_only_fields": sorted(set(changed) - set(persistable_changes)),
    "secret_persistence": "session_only" if any(
        key in _LLM_SENSITIVE_FIELDS and not is_secret_ref(value)
        for key, value in changed.items()
    ) else "reference_only",
}
```

- [ ] **步骤 4：验证 API 安全和兼容性**

运行：

```powershell
python -m pytest apps/api/tests/test_llm_config_security.py -q
python -m pytest apps/api/tests/test_api_v1_honesty.py -q
```

预期：全部 PASS；GET 仍只返回 `has_*_key` 布尔值，不返回密钥或解析值。

- [ ] **步骤 5：提交密钥修复**

```bash
git add apps/api/xagent/api/v1/system.py apps/api/tests/test_llm_config_security.py apps/api/tests/test_api_v1_honesty.py
git commit -m "fix: keep raw provider keys out of persistent overrides"
```

### 任务 5：清理历史明文覆盖文件

**文件：**
- 创建：`scripts/migrate_llm_overrides.py`
- 创建：`tests/release/test_migrate_llm_overrides.py`

- [ ] **步骤 1：编写 dry-run 和 apply 测试**

```python
def test_migration_strips_raw_secrets_and_preserves_refs(tmp_path: Path) -> None:
    target = tmp_path / "llm_config_overrides.json"
    target.write_text(json.dumps({
        "default_model": "ollama/qwen3:4b",
        "openai_api_key": "historical-raw-secret",
        "deepseek_api_key": "SECRETREF:env:DEEPSEEK_API_KEY",
    }), encoding="utf-8")
    report = migrate(target, apply=False)
    assert report.removed_fields == ("openai_api_key",)
    assert "historical-raw-secret" in target.read_text(encoding="utf-8")
    migrate(target, apply=True)
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved == {
        "deepseek_api_key": "SECRETREF:env:DEEPSEEK_API_KEY",
        "default_model": "ollama/qwen3:4b",
    }
```

- [ ] **步骤 2：确认测试失败**

运行：`python -m pytest tests/release/test_migrate_llm_overrides.py -q`

预期：FAIL，迁移模块不存在。

- [ ] **步骤 3：实现不打印值的迁移器**

定义 `MigrationReport(path: Path, removed_fields: Sequence[str], changed: bool)`；`migrate(path, apply)` 读取对象 JSON，删除四个敏感字段中的非 `SECRETREF:` 值，apply 时调用 `write_private_json`。CLI 默认 dry-run，仅打印路径、字段名和是否改变；`--apply` 才写盘。

- [ ] **步骤 4：验证迁移并处理当前历史文件**

运行：

```powershell
python -m pytest tests/release/test_migrate_llm_overrides.py -q
python scripts/migrate_llm_overrides.py data/llm_config_overrides.json
python scripts/migrate_llm_overrides.py data/llm_config_overrides.json --apply
```

预期：测试 PASS；实际文件仅在存在时处理，日志不含任何密钥值。已有外泄供应商密钥标记为需要在对应供应商后台轮换，轮换属于外部操作，不在本地脚本内自动执行。

- [ ] **步骤 5：提交迁移器**

```bash
git add scripts/migrate_llm_overrides.py tests/release/test_migrate_llm_overrides.py
git commit -m "feat: migrate plaintext LLM overrides safely"
```

### 任务 6：让安全扫描缺项即失败

**文件：**
- 修改：`tests/security/scan.py`
- 创建：`tests/security/test_scan.py`

- [ ] **步骤 1：编写结构化结果测试**

```python
def test_failed_required_check_changes_exit_code() -> None:
    results = [
        CheckResult("health", True, "200"),
        CheckResult("auth_required", False, "200"),
    ]
    assert exit_code(results) == 1


def test_rate_limit_attempts_exceed_configured_threshold() -> None:
    assert request_count_for_rate_limit(configured_limit=3) == 5
    assert request_count_for_rate_limit(configured_limit=300) == 302


def test_missing_tenant_checks_fail_closed() -> None:
    results = required_results({"health": CheckResult("health", True, "200")})
    assert {item.name for item in results if not item.passed} >= {
        "tenant_header_injection", "tenant_memory_isolation",
    }
```

- [ ] **步骤 2：运行失败测试**

运行：`python -m pytest tests/security/test_scan.py -q`

预期：FAIL，`CheckResult` 和纯函数不存在。

- [ ] **步骤 3：实现结果模型和确定性阈值**

```python
@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


REQUIRED_CHECKS = (
    "health", "nosniff", "frame_deny", "auth_required",
    "tenant_header_injection", "tenant_memory_isolation",
    "sql_injection", "rate_limit",
)


def request_count_for_rate_limit(configured_limit: int) -> int:
    return configured_limit + 2


def exit_code(results: Sequence[CheckResult]) -> int:
    return 0 if results and all(item.passed for item in results) else 1
```

`scan(host, expected_mode, configured_limit)` 返回 `list[CheckResult]`。full/enterprise 下业务端点必须 `401`；注册失败、写记忆失败、搜索失败均追加对应失败结果；限流请求次数由 CLI `--rate-limit-requests` 明确传入并要求至少一次 `429`。CLI 只在所有 `REQUIRED_CHECKS` 各出现一次且通过时返回 `0`。

- [ ] **步骤 4：运行单元与真实低阈值扫描**

运行：

```powershell
python -m pytest tests/security/test_scan.py apps/api/tests/test_security_middleware.py -q
python tests/security/scan.py --host http://127.0.0.1:8000 --expected-mode full --rate-limit-requests 3
```

预期：单元测试 PASS；以 `XAGENT_SECURITY__RATE_LIMIT_REQUESTS=3` 启动的隔离 API 上八项全部 PASS，退出码 `0`。API 未启动或任一请求异常时退出码 `1`，且只打印 URL、状态码和检查名。

- [ ] **步骤 5：提交扫描修复**

```bash
git add tests/security/scan.py tests/security/test_scan.py
git commit -m "fix: make security scan fail closed"
```

### 任务 7：锁定依赖并构建最小非 root 镜像

**文件：**
- 创建：`apps/api/requirements.lock`
- 创建：`packages/sdk-ts/package-lock.json`
- 修改：`apps/api/Dockerfile`
- 修改：`deploy/helm/values.yaml`
- 修改：`deploy/helm/templates/deployment.yaml`
- 修改：`deploy/helm/templates/worker.yaml`
- 修改：`deploy/helm/templates/job-post-deploy.yaml`
- 修改：`deploy/helm/templates/cronjob-health.yaml`
- 修改：`deploy/helm/templates/cronjob-evidence.yaml`
- 修改：`deploy/helm/templates/web.yaml`
- 创建：`tests/release/test_container_contract.py`
- 创建：`tests/release/test_helm_image_contract.py`

- [ ] **步骤 1：添加镜像和 Helm 失败合同**

```python
def test_api_runtime_image_is_non_root_and_has_no_dev_extra() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    assert "AS builder" in dockerfile
    assert '".[dev]"' not in dockerfile
    assert "USER 10001:10001" in dockerfile
    runtime = dockerfile.split("FROM python:3.11-slim AS runtime", 1)[1]
    assert "build-essential" not in runtime
    assert "git" in runtime


def test_helm_images_are_immutable() -> None:
    values = yaml.safe_load((ROOT / "deploy/helm/values.yaml").read_text(encoding="utf-8"))
    assert values["image"]["tag"] == "1.1.3"
    assert values["web"]["image"]["tag"] == "1.1.3"
    assert values["image"]["digest"] == ""
    assert "latest" not in json.dumps(values)
```

- [ ] **步骤 2：运行合同确认当前镜像不合格**

运行：`python -m pytest tests/release/test_container_contract.py tests/release/test_helm_image_contract.py -q`

预期：FAIL，报告单阶段镜像、dev extra、root 用户和 `latest` tag。

- [ ] **步骤 3：生成并验证锁文件**

运行：

```powershell
python -m pip install uv
uv pip compile apps/api/pyproject.toml --python-version 3.11 --generate-hashes --output-file apps/api/requirements.lock
npm --prefix packages/sdk-ts install --package-lock-only --ignore-scripts
python -m pip install pip-audit
pip-audit -r apps/api/requirements.lock
npm --prefix apps/web audit --omit=dev --audit-level=high
npm --prefix packages/sdk-ts audit --omit=dev --audit-level=high
```

预期：锁文件生成；三个生产依赖审计退出码 `0`。审计若报告漏洞，先在清单中把直接依赖升级到无漏洞兼容版本，重新生成锁并重跑；不使用 ignore 绕过高危漏洞。

- [ ] **步骤 4：实现多阶段非 root Dockerfile**

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY xagent ./xagent
COPY requirements.lock ./requirements.lock
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps .

FROM python:3.11-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 xagent \
    && useradd --uid 10001 --gid 10001 --no-create-home xagent
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "xagent.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

CI、根 Compose 与 `deploy/compose` 当前都以 `apps/api` 为 build context，因此 COPY 路径固定使用上述 context 内相对路径。

- [ ] **步骤 5：实现 Helm digest 优先模板**

在 `values.yaml` 为 API 和 Web 分别定义 `tag: "1.1.3"`、`digest: ""`。在 `_helpers.tpl` 添加：

```gotemplate
{{- define "xagent.image" -}}
{{- if .digest -}}
{{ printf "%s@%s" .repository .digest }}
{{- else -}}
{{ printf "%s:%s" .repository .tag }}
{{- end -}}
{{- end -}}
```

API 模板调用 `{{ include "xagent.image" .Values.image | quote }}`，Web 调用 `{{ include "xagent.image" .Values.web.image | quote }}`。这也修复 Web 错用 API tag 的现状。

- [ ] **步骤 6：构建并运行镜像合同**

运行：

```powershell
python -m pytest tests/release/test_container_contract.py tests/release/test_helm_image_contract.py -q
helm template xagent deploy/helm --set image.digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --set web.image.digest=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
docker build -f apps/api/Dockerfile -t xagent-api:commercial-kernel .
docker run --rm --entrypoint id xagent-api:commercial-kernel
```

预期：测试 PASS；Helm 输出 `repository@sha256:` 且无 `:latest`；容器 `id` 输出 `uid=10001`。

- [ ] **步骤 7：提交供应链修复**

```bash
git add apps/api/requirements.lock packages/sdk-ts/package-lock.json apps/api/Dockerfile deploy/helm tests/release/test_container_contract.py tests/release/test_helm_image_contract.py
git commit -m "build: lock dependencies and harden runtime images"
```

### 任务 8：接入 CI 商用内核门

**文件：**
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：增加 CI 合同断言**

在 `release-version` 任务中先运行：

```yaml
- name: Test release and container contracts
  run: >-
    python -m pytest
    tests/release/test_release_version_gate.py
    tests/release/test_container_contract.py
    tests/release/test_helm_image_contract.py -q
```

新增 `supply-chain` 任务，固定执行 `pip-audit -r apps/api/requirements.lock`、两个 `npm audit --omit=dev --audit-level=high`、`cargo audit --file apps/desktop/Cargo.lock`，并用 `anchore/sbom-action` 为 API/Web 镜像生成 SPDX JSON 后上传。

- [ ] **步骤 2：本地解析并复跑内核门**

运行：

```powershell
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8')); print('ci yaml ok')"
python -m pytest tests/release/test_release_version_gate.py tests/release/test_r2_preflight.py tests/release/test_migrate_llm_overrides.py tests/release/test_container_contract.py tests/release/test_helm_image_contract.py tests/security/test_scan.py apps/api/tests/test_secure_json.py apps/api/tests/test_llm_config_security.py -q
```

预期：输出 `ci yaml ok`；所有指定测试 PASS。

- [ ] **步骤 3：提交 CI 门**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: enforce commercial kernel gates"
```

## 本计划完成判定

运行以下命令必须全部通过，且输出不得包含真实 secret：

```powershell
python scripts/verify_release_versions.py --tag v1.1.3
python -m pytest tests/release/test_release_version_gate.py tests/release/test_r2_preflight.py tests/release/test_migrate_llm_overrides.py tests/release/test_container_contract.py tests/release/test_helm_image_contract.py tests/security/test_scan.py apps/api/tests/test_secure_json.py apps/api/tests/test_llm_config_security.py -q
pip-audit -r apps/api/requirements.lock
npm --prefix apps/web audit --omit=dev --audit-level=high
npm --prefix packages/sdk-ts audit --omit=dev --audit-level=high
cargo audit --file apps/desktop/Cargo.lock
```
