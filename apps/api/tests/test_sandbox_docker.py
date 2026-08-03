"""Docker 沙箱（RFC-001 L1）单元测试：全部 mock docker SDK，不需要真 daemon。

覆盖：容器创建参数（network/readonly/limits/timeout/destroy）、factory 按配置选择、
生产校验拦截、tools 层分发路由。
"""

from __future__ import annotations

import pytest

from xagent.adapters.sandbox.base import DisabledSandbox, get_sandbox, reset_sandbox
from xagent.adapters.sandbox.docker_sandbox import (
    DockerSandbox,
    SandboxUnavailableError,
)


# ── fake docker SDK ──────────────────────────────────────────────


class _FakeContainer:
    def __init__(
        self,
        *,
        wait_result: dict | None = None,
        wait_exc: Exception | None = None,
        logs: tuple[bytes, bytes] = (b"hello\n", b""),
    ) -> None:
        self._wait_result = wait_result if wait_result is not None else {"StatusCode": 0}
        self._wait_exc = wait_exc
        self._logs = logs
        self.started = False
        self.killed = False
        self.removed = False
        self.remove_force: bool | None = None
        self.wait_timeout: int | None = None
        self.logs_calls: list[tuple[bool, bool]] = []

    def start(self) -> None:
        self.started = True

    def wait(self, timeout: int | None = None) -> dict:
        self.wait_timeout = timeout
        if self._wait_exc is not None:
            raise self._wait_exc
        return self._wait_result

    def logs(self, *, stdout: bool, stderr: bool) -> bytes:
        """SDK 7.x 兼容签名：无 demux 参数，分流调用返回单路字节流。"""
        self.logs_calls.append((stdout, stderr))
        assert stdout != stderr, "沙箱必须分流调用 logs()（SDK 7.x 已移除 demux）"
        return self._logs[0] if stdout else self._logs[1]

    def kill(self) -> None:
        self.killed = True

    def remove(self, force: bool = False) -> None:
        self.removed = True
        self.remove_force = force


class _FakeContainers:
    def __init__(self, container: _FakeContainer) -> None:
        self._container = container
        self.create_image: str | None = None
        self.create_kwargs: dict | None = None

    def create(self, image: str, **kwargs):
        self.create_image = image
        self.create_kwargs = kwargs
        return self._container


class _FakeClient:
    def __init__(self, container: _FakeContainer) -> None:
        self.containers = _FakeContainers(container)


def _make_sandbox(
    container: _FakeContainer, **overrides
) -> tuple[DockerSandbox, _FakeClient]:
    client = _FakeClient(container)
    sandbox = DockerSandbox(client_factory=lambda: client, **overrides)
    return sandbox, client


# ── 容器创建参数 / 生命周期 ──────────────────────────────────────


async def test_container_params_network_readonly_limits() -> None:
    """RFC-001 L1：--network=none、只读根 fs、内存/CPU 限额、用后销毁。"""
    container = _FakeContainer()
    sandbox, client = _make_sandbox(
        container,
        image="python:3.11-slim",
        mem_limit="512m",
        cpu_quota=100000,
        network_disabled=True,
        readonly_rootfs=True,
    )
    res = await sandbox.run_code("python", "print('hi')", timeout=20)

    assert res.ok is True
    assert res.stdout == "hello\n"
    assert res.exit_code == 0

    kwargs = client.containers.create_kwargs
    assert client.containers.create_image == "python:3.11-slim"
    assert kwargs["network_disabled"] is True      # --network=none
    assert kwargs["read_only"] is True             # --read-only
    assert kwargs["mem_limit"] == "512m"
    assert kwargs["cpu_quota"] == 100000
    assert kwargs["detach"] is True
    assert kwargs["command"] == ["python", "-c", "print('hi')"]

    # 执行超时传到 wait；容器用后强制销毁
    assert container.wait_timeout == 20
    assert container.started is True
    assert container.removed is True
    assert container.remove_force is True


async def test_shell_language_uses_sh_c() -> None:
    container = _FakeContainer()
    sandbox, client = _make_sandbox(container)
    res = await sandbox.run_code("shell", "echo hi", timeout=10)
    assert res.ok is True
    assert client.containers.create_kwargs["command"] == ["sh", "-c", "echo hi"]


async def test_workspace_mounted_readonly() -> None:
    container = _FakeContainer()
    sandbox, client = _make_sandbox(container, workspace="D:/ws")
    await sandbox.run_code("python", "print(1)")
    kwargs = client.containers.create_kwargs
    assert kwargs["volumes"] == {"D:/ws": {"bind": "/work", "mode": "ro"}}
    assert kwargs["working_dir"] == "/work"


async def test_nonzero_exit_code_propagates() -> None:
    container = _FakeContainer(
        wait_result={"StatusCode": 2}, logs=(b"", b"boom\n")
    )
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("python", "raise SystemExit(2)")
    assert res.ok is False
    assert res.exit_code == 2
    assert "boom" in (res.error or "")
    assert container.removed is True


async def test_timeout_kills_container_and_reports() -> None:
    """wait 超时（如 requests ReadTimeout）：kill 容器、报错、仍然销毁。"""
    container = _FakeContainer(wait_exc=TimeoutError("read timeout"))
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("python", "import time; time.sleep(999)", timeout=5)
    assert res.ok is False
    assert "超时" in (res.error or "")
    assert container.killed is True
    assert container.removed is True


async def test_output_truncated() -> None:
    big = b"x" * 100_000
    container = _FakeContainer(logs=(big, b""))
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("python", "print('x'*100000)")
    assert res.ok is True
    assert "截断" in res.stdout
    assert len(res.stdout) < 100_000


async def test_daemon_unavailable_clear_error() -> None:
    """daemon 不可达（如 Windows npipe 连接失败）：明确报错，不抛异常。"""
    sandbox = DockerSandbox(
        client_factory=lambda: (_ for _ in ()).throw(
            SandboxUnavailableError(
                "Docker 沙箱不可用：无法连接 Docker daemon（npipe ...）"
            )
        )
    )
    res = await sandbox.run_code("python", "print(1)")
    assert res.ok is False
    assert "Docker 沙箱不可用" in (res.error or "")


async def test_unsupported_language() -> None:
    container = _FakeContainer()
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("ruby", "puts 1")
    assert res.ok is False
    assert "暂不支持语言" in (res.error or "")


async def test_health() -> None:
    container = _FakeContainer()
    sandbox, _ = _make_sandbox(container)
    assert await sandbox.health() is True

    bad = DockerSandbox(
        client_factory=lambda: (_ for _ in ()).throw(SandboxUnavailableError("x"))
    )
    assert await bad.health() is False


# ── factory 按配置选择 ───────────────────────────────────────────


def _set_backend(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_SANDBOX__BACKEND", value)
    get_settings.cache_clear()
    reset_sandbox()


def test_factory_default_disabled() -> None:
    sandbox = get_sandbox()
    assert isinstance(sandbox, DisabledSandbox)
    assert sandbox.backend == "disabled"


def test_factory_docker_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAGENT_SANDBOX__DOCKER_IMAGE", "xagent-sandbox:py3.12")
    monkeypatch.setenv("XAGENT_SANDBOX__MEM_LIMIT", "256m")
    monkeypatch.setenv("XAGENT_SANDBOX__CPU_QUOTA", "50000")
    _set_backend(monkeypatch, "docker")
    sandbox = get_sandbox()
    assert isinstance(sandbox, DockerSandbox)
    assert sandbox.backend == "docker"
    assert sandbox._image == "xagent-sandbox:py3.12"
    assert sandbox._mem_limit == "256m"
    assert sandbox._cpu_quota == 50000
    assert sandbox._network_disabled is True
    assert sandbox._readonly_rootfs is True


# E2B 后端（L2）测试见 test_sandbox_e2b.py


# ── 生产校验拦截 ─────────────────────────────────────────────────


def _production_settings(**sandbox_kw):
    from xagent.infra.settings import (
        RunMode,
        SandboxSettings,
        Settings,
        ToolsSettings,
    )

    return Settings(
        mode=RunMode.full,
        cors_origins=["https://app.example.com"],
        tools=ToolsSettings(enable_shell=True),
        sandbox=SandboxSettings(**sandbox_kw),
    )


def test_production_rejects_shell_exec_without_sandbox() -> None:
    s = _production_settings(backend="disabled")
    s.security.jwt_secret = "x" * 40
    problems = s.validate_for_production()
    assert any("沙箱" in p and "docker" in p for p in problems)


def test_production_accepts_shell_exec_with_docker_sandbox() -> None:
    s = _production_settings(backend="docker")
    s.security.jwt_secret = "x" * 40
    assert s.validate_for_production() == []


def test_production_rejects_python_exec_without_sandbox() -> None:
    from xagent.infra.settings import RunMode, Settings

    s = _production_settings(backend="disabled")
    s.security.jwt_secret = "x" * 40
    s.tools.enable_shell = False
    s.tools.enable_python_exec = True
    problems = s.validate_for_production()
    assert any("沙箱" in p for p in problems)
    # lite 模式不受该校验约束
    lite = Settings(mode=RunMode.lite)
    lite.tools.enable_shell = True
    assert lite.validate_for_production() == []


# ── tools 层分发路由 ─────────────────────────────────────────────


class _FakeSandbox:
    backend = "docker"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    async def run_code(self, language: str, code: str, *, timeout: int = 30):
        from xagent.adapters.sandbox.base import SandboxResult

        self.calls.append((language, code, timeout))
        return SandboxResult(ok=True, stdout="sandbox-out\n", exit_code=0)

    async def health(self) -> bool:
        return True


def _ctx():
    from xagent.adapters.tools.base import ToolContext
    from xagent.enterprise.auth.principal import Principal

    return ToolContext(
        principal=Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    )


def _enable_tool(monkeypatch: pytest.MonkeyPatch, env: str, fake) -> None:
    from xagent.infra.settings import get_settings

    monkeypatch.setenv(env, "true")
    get_settings.cache_clear()
    monkeypatch.setattr("xagent.adapters.sandbox.base.get_sandbox", lambda: fake)


async def test_shell_exec_routes_to_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENABLE_SHELL=true 且 backend=docker：命令路由进沙箱，不在宿主机执行。"""
    from xagent.adapters.tools.power_tools import ShellExecTool

    fake = _FakeSandbox()
    _enable_tool(monkeypatch, "XAGENT_TOOLS__ENABLE_SHELL", fake)
    res = await ShellExecTool().run({"command": "echo hi"}, _ctx())
    assert res.ok is True
    assert "sandbox-out" in (res.output or "")
    assert fake.calls == [("shell", "echo hi", 120)]


async def test_shell_exec_default_disabled_unaffected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认（shell 禁用）：门禁照常拦截，不触碰沙箱。"""
    from xagent.adapters.tools.power_tools import ShellExecTool

    fake = _FakeSandbox()
    monkeypatch.setattr("xagent.adapters.sandbox.base.get_sandbox", lambda: fake)
    res = await ShellExecTool().run({"command": "echo hi"}, _ctx())
    assert res.ok is False
    assert "已被配置禁用" in (res.error or "")
    assert fake.calls == []


async def test_shell_exec_sandbox_failure_no_host_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """沙箱报错时不降级到宿主机执行。"""
    from xagent.adapters.sandbox.base import SandboxResult
    from xagent.adapters.tools.power_tools import ShellExecTool

    class _FailSandbox(_FakeSandbox):
        async def run_code(self, language, code, *, timeout=30):
            return SandboxResult(ok=False, error="Docker 沙箱不可用: no daemon")

    _enable_tool(monkeypatch, "XAGENT_TOOLS__ENABLE_SHELL", _FailSandbox())
    res = await ShellExecTool().run({"command": "echo hi"}, _ctx())
    assert res.ok is False
    assert "沙箱" in (res.error or "")


async def test_python_exec_routes_to_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    from xagent.adapters.tools.power_tools import PythonExecTool

    fake = _FakeSandbox()
    _enable_tool(monkeypatch, "XAGENT_TOOLS__ENABLE_PYTHON_EXEC", fake)
    res = await PythonExecTool().run({"code": "print(1)"}, _ctx())
    assert res.ok is True
    assert "sandbox-out" in (res.output or "")
    assert fake.calls == [("python", "print(1)", 30)]


async def test_python_exec_disabled_backend_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """backend=disabled（L0）时 python_exec 拒绝执行，不回退宿主机子进程（RFC-001）。"""
    from xagent.adapters.sandbox.base import DisabledSandbox
    from xagent.adapters.tools.power_tools import PythonExecTool

    _enable_tool(monkeypatch, "XAGENT_TOOLS__ENABLE_PYTHON_EXEC", DisabledSandbox())
    res = await PythonExecTool().run({"code": "print(1)"}, _ctx())
    assert res.ok is False
    assert "拒绝执行" in (res.error or "")
    assert "disabled" in (res.error or "")
    assert "XAGENT_SANDBOX__BACKEND" in (res.error or "")


async def test_python_exec_sandbox_failure_no_host_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """沙箱后端报错时不降级到宿主机执行。"""
    from xagent.adapters.sandbox.base import SandboxResult
    from xagent.adapters.tools.power_tools import PythonExecTool

    class _FailSandbox(_FakeSandbox):
        async def run_code(self, language, code, *, timeout=30):
            return SandboxResult(ok=False, error="Docker 沙箱不可用: no daemon")

    _enable_tool(monkeypatch, "XAGENT_TOOLS__ENABLE_PYTHON_EXEC", _FailSandbox())
    res = await PythonExecTool().run({"code": "print(1)"}, _ctx())
    assert res.ok is False
    assert "沙箱" in (res.error or "")


# ── stdout/stderr 分流回收（SDK 7.x，无 demux）───────────────────


async def test_logs_split_calls_no_demux() -> None:
    """SDK 7.x 兼容：分流两次 logs() 调用，stdout/stderr 分别回收。"""
    container = _FakeContainer(logs=(b"out-line\n", b"err-line\n"))
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("python", "print(1)")

    assert res.ok is True
    assert res.stdout == "out-line\n"
    assert res.stderr == "err-line\n"
    # 必须分流调用（不能 stdout/stderr 同 True 的合并流，更不能用已移除的 demux）
    assert (True, False) in container.logs_calls
    assert (False, True) in container.logs_calls


async def test_logs_none_output_tolerated() -> None:
    """logs() 返回 None（空流）时不崩溃。"""

    class _NoneLogs(_FakeContainer):
        def logs(self, *, stdout: bool, stderr: bool) -> bytes:
            self.logs_calls.append((stdout, stderr))
            return None

    container = _NoneLogs()
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("python", "pass")
    assert res.ok is True
    assert res.stdout == ""
    assert res.stderr == ""


# ── 多路复用帧防御性解帧 ─────────────────────────────────────────


def _mux_frame(stream_id: int, payload: bytes) -> bytes:
    return bytes([stream_id, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


async def test_mux_framed_logs_decoded() -> None:
    """防御：若 daemon 返回 8 字节多路复用帧（旧 daemon/双流），正确解帧。"""

    class _MuxLogs(_FakeContainer):
        def logs(self, *, stdout: bool, stderr: bool) -> bytes:
            self.logs_calls.append((stdout, stderr))
            if stdout:
                return _mux_frame(1, b"framed-out\n")
            return _mux_frame(2, b"framed-err\n")

    container = _MuxLogs(wait_result={"StatusCode": 1})
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("python", "raise SystemExit(1)")
    assert res.ok is False
    assert res.stdout == "framed-out\n"
    assert res.stderr == "framed-err\n"
    assert "framed-err" in (res.error or "")


async def test_plain_output_not_mistaken_for_frames() -> None:
    """普通输出首字节恰为 0/1/2 时不误判为帧流。"""
    # 首字节 0x01 但不是合法完整帧 → 原样返回
    container = _FakeContainer(logs=(b"\x01not-a-frame", b""))
    sandbox, _ = _make_sandbox(container)
    res = await sandbox.run_code("python", "pass")
    assert res.stdout == "\x01not-a-frame"
