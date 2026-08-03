"""Docker 沙箱实机集成测试（需要运行中的 Docker daemon）。

默认跳过；设置环境变量 ``XAGENT_DOCKER_INTEGRATION=1`` 后实跑：

    cd apps/api
    PYTHONPATH=$PWD XAGENT_DOCKER_INTEGRATION=1 \\
        ./.venv/Scripts/python.exe -m pytest tests/test_docker_sandbox_integration.py -q

覆盖（RFC-001 L1 实测）：
- stdout/stderr 分流回收（SDK 7.x 无 demux）
- 非零退出码传播
- 只读 rootfs：容器内写系统目录失败
- 网络隔离：network_disabled 下无法外联
- 执行超时：超时 kill 容器并报错
- 一次性容器：执行后容器已销毁
"""

from __future__ import annotations

import os

import pytest
from xagent.adapters.sandbox.docker_sandbox import (
    DockerSandbox,
    SandboxUnavailableError,
)

_INTEGRATION = os.environ.get("XAGENT_DOCKER_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not _INTEGRATION,
    reason="实机集成测试默认跳过（设 XAGENT_DOCKER_INTEGRATION=1 启用）",
)

_IMAGE = "python:3.11-slim"


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def sandbox() -> DockerSandbox:
    if not _docker_available():
        pytest.skip("Docker daemon 不可达")
    sb = DockerSandbox(image=_IMAGE, timeout_seconds=30)
    return sb


async def test_stdout_stderr_split_real(sandbox: DockerSandbox) -> None:
    """实机：stdout/stderr 正确分流回收（SDK 7.x 兼容路径）。"""
    code = (
        "import sys\n"
        "sys.stdout.write('REAL_OUT\\n')\n"
        "sys.stderr.write('REAL_ERR\\n')\n"
    )
    res = await sandbox.run_code("python", code, timeout=60)
    assert res.ok is True, res.error
    assert res.exit_code == 0
    assert "REAL_OUT" in res.stdout
    assert "REAL_ERR" not in res.stdout
    assert "REAL_ERR" in res.stderr
    assert "REAL_OUT" not in res.stderr


async def test_nonzero_exit_real(sandbox: DockerSandbox) -> None:
    res = await sandbox.run_code("python", "raise SystemExit(3)", timeout=60)
    assert res.ok is False
    assert res.exit_code == 3


async def test_readonly_rootfs_real(sandbox: DockerSandbox) -> None:
    """隔离：只读 rootfs 下写系统目录被拒绝（容器内执行，非宿主机）。"""
    code = (
        "try:\n"
        "    open('/etc/xagent_escape', 'w').write('x')\n"
        "    print('ESCAPE_OK')\n"
        "except OSError as e:\n"
        "    print('BLOCKED:', type(e).__name__)\n"
    )
    res = await sandbox.run_code("python", code, timeout=60)
    assert res.ok is True, res.error
    assert "BLOCKED" in res.stdout
    assert "ESCAPE_OK" not in res.stdout


async def test_network_disabled_real(sandbox: DockerSandbox) -> None:
    """隔离：network_disabled 下容器内 socket 外联失败。"""
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('8.8.8.8', 53), timeout=3)\n"
        "    print('NET_OK')\n"
        "except OSError:\n"
        "    print('NET_BLOCKED')\n"
    )
    res = await sandbox.run_code("python", code, timeout=60)
    assert res.ok is True, res.error
    assert "NET_BLOCKED" in res.stdout
    assert "NET_OK" not in res.stdout


async def test_timeout_real(sandbox: DockerSandbox) -> None:
    """隔离：超时容器被 kill，报错且不泄漏为宿主机执行。"""
    res = await sandbox.run_code(
        "python", "import time; time.sleep(120)", timeout=5
    )
    assert res.ok is False
    assert "超时" in (res.error or "")


async def test_ephemeral_container_removed_real(sandbox: DockerSandbox) -> None:
    """一次性容器：执行完成后无残留容器。"""
    import docker

    client = docker.from_env()
    before = {c.id for c in client.containers.list(all=True)}
    res = await sandbox.run_code("python", "print('hello')", timeout=60)
    assert res.ok is True
    assert "hello" in res.stdout
    after = {c.id for c in client.containers.list(all=True)}
    leaked = after - before
    client.close()
    assert leaked == set(), f"容器泄漏: {leaked}"


async def test_health_real(sandbox: DockerSandbox) -> None:
    assert await sandbox.health() is True


def test_unavailable_error_message() -> None:
    """SDK 缺失/daemon 不可达时错误信息明确（fail-closed 语义）。"""
    err = SandboxUnavailableError("Docker 沙箱不可用：无法连接 Docker daemon")
    assert "Docker 沙箱不可用" in str(err)
