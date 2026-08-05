"""E2B 云沙箱（RFC-001 L2）单元测试：全部 mock，不触网、不需要真实 API key。

覆盖：SDK 通道（创建参数/执行/截断/超时销毁）、REST 通道（httpx 回退）、
错误路径（无 key / SDK 与 REST 均缺失 / HTTP 失败）、factory 选择、生产校验兼容。
"""

from __future__ import annotations

import sys
import types

import pytest
from xagent.adapters.sandbox.base import (
    UnsupportedBackendSandbox,
    get_sandbox,
    reset_sandbox,
)
from xagent.adapters.sandbox.e2b_sandbox import E2BSandbox

# ── fake e2b_code_interpreter SDK ────────────────────────────────


class _FakeLogs:
    def __init__(self, stdout=None, stderr=None) -> None:
        self.stdout = stdout if stdout is not None else ["hello"]
        self.stderr = stderr if stderr is not None else []


class _FakeExecution:
    def __init__(self, logs=None, error=None) -> None:
        self.logs = logs if logs is not None else _FakeLogs()
        self.error = error


class _FakeCommandResult:
    def __init__(self, stdout="sh-out\n", stderr="", exit_code=0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


class _FakeCommands:
    def __init__(self, result=None, exc=None) -> None:
        self._result = result if result is not None else _FakeCommandResult()
        self._exc = exc
        self.calls: list[tuple[str, int]] = []

    def run(self, cmd: str, timeout: int = 30):
        self.calls.append((cmd, timeout))
        if self._exc is not None:
            raise self._exc
        return self._result


class _FakeSdkSandbox:
    """模拟 e2b_code_interpreter.Sandbox 实例。"""

    def __init__(self, execution=None, run_exc=None, commands=None) -> None:
        self._execution = execution if execution is not None else _FakeExecution()
        self._run_exc = run_exc
        self.commands = commands if commands is not None else _FakeCommands()
        self.run_calls: list[tuple[str, int]] = []
        self.killed = False

    def run_code(self, code: str, timeout: int = 30):
        self.run_calls.append((code, timeout))
        if self._run_exc is not None:
            raise self._run_exc
        return self._execution

    def kill(self) -> None:
        self.killed = True


def _make_sdk_sandbox(fake: _FakeSdkSandbox, **overrides) -> E2BSandbox:
    overrides.setdefault("api_key", "test-key")
    return E2BSandbox(sdk_factory=lambda: fake, **overrides)


# ── SDK 通道：执行 / 生命周期 ────────────────────────────────────


async def test_sdk_run_code_success_and_destroy() -> None:
    fake = _FakeSdkSandbox()
    sandbox = _make_sdk_sandbox(fake)
    res = await sandbox.run_code("python", "print('hi')", timeout=20)

    assert res.ok is True
    assert res.stdout == "hello"
    assert res.exit_code == 0
    assert fake.run_calls == [("print('hi')", 20)]  # 超时透传 SDK
    assert fake.killed is True                      # 用后销毁


async def test_sdk_create_params_template_key() -> None:
    """创建参数：template / api_key / timeout 透传 SDK create。"""
    created: dict = {}

    class _FakeE2BModule(types.ModuleType):
        class Sandbox:  # noqa: D106
            @staticmethod
            def create(template=None, api_key=None, timeout=None):
                created.update(template=template, api_key=api_key, timeout=timeout)
                return _FakeSdkSandbox()

    fake_mod = _FakeE2BModule("e2b_code_interpreter")
    old = sys.modules.get("e2b_code_interpreter")
    sys.modules["e2b_code_interpreter"] = fake_mod
    try:
        sandbox = E2BSandbox(
            api_key="k-1", template="my-tpl", base_url="https://x", timeout_seconds=45
        )
        assert sandbox._resolve_sdk_factory() is not None  # 走 SDK 通道
        res = await sandbox.run_code("python", "print(1)")
        assert res.ok is True
    finally:
        if old is None:
            sys.modules.pop("e2b_code_interpreter", None)
        else:
            sys.modules["e2b_code_interpreter"] = old

    assert created == {"template": "my-tpl", "api_key": "k-1", "timeout": 45}


async def test_sdk_shell_routes_to_commands() -> None:
    cmds = _FakeCommands(result=_FakeCommandResult(stdout="sh-out\n", exit_code=0))
    fake = _FakeSdkSandbox(commands=cmds)
    sandbox = _make_sdk_sandbox(fake)
    res = await sandbox.run_code("shell", "echo hi", timeout=10)
    assert res.ok is True
    assert res.stdout == "sh-out\n"
    assert cmds.calls == [("echo hi", 10)]
    assert fake.killed is True


async def test_sdk_execution_error_propagates() -> None:
    fake = _FakeSdkSandbox(
        execution=_FakeExecution(logs=_FakeLogs(stdout=[], stderr=["boom"]), error="NameError: x")
    )
    sandbox = _make_sdk_sandbox(fake)
    res = await sandbox.run_code("python", "x")
    assert res.ok is False
    assert "NameError" in (res.error or "")
    assert fake.killed is True


async def test_sdk_timeout_destroys_sandbox() -> None:
    class TimeoutException(Exception):
        pass

    fake = _FakeSdkSandbox(run_exc=TimeoutException("sandbox timeout"))
    sandbox = _make_sdk_sandbox(fake)
    res = await sandbox.run_code("python", "while True: pass", timeout=5)
    assert res.ok is False
    assert "超时" in (res.error or "")
    assert fake.killed is True


async def test_sdk_output_truncated() -> None:
    big = ["x" * 100_000]
    fake = _FakeSdkSandbox(execution=_FakeExecution(logs=_FakeLogs(stdout=big)))
    sandbox = _make_sdk_sandbox(fake)
    res = await sandbox.run_code("python", "print('x'*100000)")
    assert res.ok is True
    assert "截断" in res.stdout
    assert len(res.stdout) < 100_000
    assert fake.killed is True


async def test_sdk_destroy_called_even_on_unexpected_error() -> None:
    fake = _FakeSdkSandbox(run_exc=RuntimeError("boom"))
    sandbox = _make_sdk_sandbox(fake)
    res = await sandbox.run_code("python", "print(1)")
    assert res.ok is False
    assert "E2B 沙箱执行失败" in (res.error or "")
    assert fake.killed is True


# ── REST 通道（httpx 回退，fake client） ─────────────────────────


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttpClient:
    """模拟 httpx.Client（base_url + X-API-Key 头由工厂外部保证）。"""

    def __init__(
        self,
        *,
        create_resp=None,
        exec_resp=None,
        create_exc=None,
        exec_exc=None,
    ) -> None:
        self._create_resp = create_resp or _FakeResponse(
            payload={"sandboxID": "sbx-123"}
        )
        self._exec_resp = exec_resp or _FakeResponse(
            payload={"logs": {"stdout": ["hello"], "stderr": []}, "error": None}
        )
        self._create_exc = create_exc
        self._exec_exc = exec_exc
        self.posts: list[tuple[str, dict, int | None]] = []
        self.deleted: list[str] = []
        self.closed = False

    def post(self, path: str, json=None, timeout=None):
        self.posts.append((path, json, timeout))
        if path == "/sandboxes":
            if self._create_exc is not None:
                raise self._create_exc
            return self._create_resp
        if self._exec_exc is not None:
            raise self._exec_exc
        return self._exec_resp

    def delete(self, path: str):
        self.deleted.append(path)
        return _FakeResponse()

    def close(self) -> None:
        self.closed = True


def _make_rest_sandbox(client: _FakeHttpClient, **overrides) -> E2BSandbox:
    """强制走 REST 通道：sdk_factory 不注入且屏蔽 SDK 导入。"""
    overrides.setdefault("api_key", "test-key")
    sandbox = E2BSandbox(
        sdk_factory=None,
        http_client_factory=lambda: client,
        **overrides,
    )
    # 本环境未安装 e2b_code_interpreter，_resolve_sdk_factory 自然返回 None
    assert sandbox._resolve_sdk_factory() is None
    return sandbox


async def test_rest_create_execute_destroy_flow() -> None:
    client = _FakeHttpClient()
    sandbox = _make_rest_sandbox(client, template="code-interpreter")
    res = await sandbox.run_code("python", "print('hi')", timeout=15)

    assert res.ok is True
    assert res.stdout == "hello"
    # 创建参数：templateID + timeout
    assert client.posts[0] == (
        "/sandboxes",
        {"templateID": "code-interpreter", "timeout": 15},
        None,
    )
    # 执行：POST /sandboxes/{id}/code
    assert client.posts[1][0] == "/sandboxes/sbx-123/code"
    assert client.posts[1][1] == {"code": "print('hi')"}
    assert client.posts[1][2] == 15  # 执行超时透传
    # 用后销毁
    assert client.deleted == ["/sandboxes/sbx-123"]


async def test_rest_shell_wrapped_via_subprocess() -> None:
    client = _FakeHttpClient()
    sandbox = _make_rest_sandbox(client)
    res = await sandbox.run_code("shell", "echo hi")
    assert res.ok is True
    payload = client.posts[1][1]["code"]
    assert "subprocess.run('echo hi'" in payload


async def test_rest_output_truncated() -> None:
    client = _FakeHttpClient(
        exec_resp=_FakeResponse(
            payload={"logs": {"stdout": ["x" * 100_000], "stderr": []}}
        )
    )
    sandbox = _make_rest_sandbox(client)
    res = await sandbox.run_code("python", "print('x'*100000)")
    assert res.ok is True
    assert "截断" in res.stdout
    assert len(res.stdout) < 100_000
    assert client.deleted == ["/sandboxes/sbx-123"]


async def test_rest_exec_error_field() -> None:
    client = _FakeHttpClient(
        exec_resp=_FakeResponse(
            payload={"logs": {"stdout": [], "stderr": ["boom"]},
                     "error": {"message": "NameError: x"}}
        )
    )
    sandbox = _make_rest_sandbox(client)
    res = await sandbox.run_code("python", "x")
    assert res.ok is False
    assert "NameError" in (res.error or "")
    assert client.deleted == ["/sandboxes/sbx-123"]


async def test_rest_http_failure_still_destroys() -> None:
    client = _FakeHttpClient(
        exec_resp=_FakeResponse(status_code=500, text="internal error")
    )
    sandbox = _make_rest_sandbox(client)
    res = await sandbox.run_code("python", "print(1)")
    assert res.ok is False
    assert "HTTP 500" in (res.error or "")
    assert client.deleted == ["/sandboxes/sbx-123"]


async def test_rest_create_failure_clear_error_no_delete() -> None:
    client = _FakeHttpClient(create_exc=ConnectionError("refused"))
    sandbox = _make_rest_sandbox(client)
    res = await sandbox.run_code("python", "print(1)")
    assert res.ok is False
    assert "创建失败" in (res.error or "")
    assert client.deleted == []  # 未创建成功，无需销毁


async def test_rest_exec_timeout_destroys() -> None:
    class TimeoutException(Exception):
        pass

    client = _FakeHttpClient(exec_exc=TimeoutException("read timeout"))
    sandbox = _make_rest_sandbox(client)
    res = await sandbox.run_code("python", "while True: pass", timeout=5)
    assert res.ok is False
    assert "超时" in (res.error or "")
    assert client.deleted == ["/sandboxes/sbx-123"]


# ── 错误路径：无 key / 双通道缺失 / 语言校验 ─────────────────────


async def test_no_api_key_clear_error() -> None:
    sandbox = E2BSandbox(api_key="", sdk_factory=lambda: _FakeSdkSandbox())
    res = await sandbox.run_code("python", "print(1)")
    assert res.ok is False
    assert "未配置 API key" in (res.error or "")
    assert "XAGENT_SANDBOX__E2B_API_KEY" in (res.error or "")


def test_api_key_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2B_API_KEY", "env-key")
    sandbox = E2BSandbox()
    assert sandbox._api_key == "env-key"
    # 显式参数优先于环境变量
    assert E2BSandbox(api_key="explicit")._api_key == "explicit"


async def test_both_channels_missing_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK 缺失且 httpx 也不可用：明确中文报错，不静默降级。"""
    monkeypatch.setitem(sys.modules, "httpx", None)  # 模拟 httpx 导入失败
    sandbox = E2BSandbox(api_key="k")  # 本环境无 e2b_code_interpreter
    assert sandbox._resolve_sdk_factory() is None
    res = await sandbox.run_code("python", "print(1)")
    assert res.ok is False
    assert "E2B 沙箱不可用" in (res.error or "")
    assert "e2b-code-interpreter" in (res.error or "")


async def test_health() -> None:
    ok_sdk = E2BSandbox(api_key="k", sdk_factory=lambda: _FakeSdkSandbox())
    assert await ok_sdk.health() is True
    ok_rest = E2BSandbox(api_key="k", http_client_factory=lambda: _FakeHttpClient())
    assert await ok_rest.health() is True
    no_key = E2BSandbox(api_key="", sdk_factory=lambda: _FakeSdkSandbox())
    assert await no_key.health() is False


async def test_unsupported_language_and_empty_code() -> None:
    sandbox = _make_sdk_sandbox(_FakeSdkSandbox())
    res = await sandbox.run_code("ruby", "puts 1")
    assert res.ok is False
    assert "暂不支持语言" in (res.error or "")
    res = await sandbox.run_code("python", "   ")
    assert res.ok is False
    assert "不能为空" in (res.error or "")


# ── factory 按配置选择 ───────────────────────────────────────────


def _set_backend(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_SANDBOX__BACKEND", value)
    get_settings.cache_clear()
    reset_sandbox()


def test_factory_e2b_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAGENT_SANDBOX__E2B_API_KEY", "cfg-key")
    monkeypatch.setenv("XAGENT_SANDBOX__E2B_TEMPLATE", "custom-tpl")
    monkeypatch.setenv("XAGENT_SANDBOX__E2B_BASE_URL", "https://e2b.self-hosted.example.com")
    monkeypatch.setenv("XAGENT_SANDBOX__TIMEOUT_SECONDS", "60")
    _set_backend(monkeypatch, "e2b")
    sandbox = get_sandbox()
    assert isinstance(sandbox, E2BSandbox)
    assert sandbox.backend == "e2b"
    assert sandbox._api_key == "cfg-key"
    assert sandbox._template == "custom-tpl"
    assert sandbox._base_url == "https://e2b.self-hosted.example.com"
    assert sandbox._timeout_seconds == 60


def test_factory_e2b_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    _set_backend(monkeypatch, "e2b")
    sandbox = get_sandbox()
    assert isinstance(sandbox, E2BSandbox)
    assert sandbox._template == "code-interpreter"
    assert sandbox._base_url == "https://api.e2b.dev"
    assert sandbox._api_key == ""  # 未配 key：health False / run_code 明确报错


async def test_factory_e2b_no_key_run_code_errors_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    _set_backend(monkeypatch, "e2b")
    res = await get_sandbox().run_code("python", "print(1)")
    assert res.ok is False
    assert "未配置 API key" in (res.error or "")


def test_factory_unknown_backend_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_backend(monkeypatch, "kubernetes")
    sandbox = get_sandbox()
    assert isinstance(sandbox, UnsupportedBackendSandbox)
    assert sandbox.backend == "kubernetes"


# ── 生产校验兼容 ─────────────────────────────────────────────────


def test_production_accepts_shell_exec_with_e2b_sandbox() -> None:
    from xagent.infra.settings import (
        RunMode,
        SandboxSettings,
        Settings,
        ToolsSettings,
    )

    s = Settings(
        mode=RunMode.full,
        cors_origins=["https://app.example.com"],
        tools=ToolsSettings(enable_shell=True),
        sandbox=SandboxSettings(backend="e2b", e2b_api_key="k"),
    )
    s.security.jwt_secret = "x" * 40
    assert s.validate_for_production() == []
