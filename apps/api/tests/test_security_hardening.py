"""P0 安全加固测试：默认鉴权、登录限流、默认口令改密标记、shell 工具门禁。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.enterprise.auth.login_rate_limit import reset_login_rate_limiter
from xagent.enterprise.auth.users import reset_user_store
from xagent.main import create_app


@pytest.fixture(autouse=True)
def _reset_security_state():
    reset_login_rate_limiter()
    reset_user_store()
    yield
    reset_login_rate_limiter()
    reset_user_store()


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─── 1. 默认鉴权开启 ────────────────────────────────────────────────


async def test_anonymous_blocked_by_default(client: AsyncClient) -> None:
    """lite 默认 auth_required=True：无凭据访问业务端点应 401。"""
    resp = await client.post("/api/v1/agents/run", json={"goal": "hi"})
    assert resp.status_code == 401
    resp = await client.get("/api/v1/agents/roles")
    assert resp.status_code == 401


async def test_valid_token_still_works(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    resp = await client.get(
        "/api/v1/agents/roles", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200


async def test_escape_hatch_anonymous_has_no_roles(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """显式关闭鉴权后：匿名可访问公开端点，但角色为空、写/执行操作 403。"""
    from xagent.infra.settings import get_settings

    get_settings().security.require_auth = False
    try:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_anonymous"] is True
        assert body["roles"] == []

        # 匿名空角色 -> agents/run（agent:execute）必须 403
        resp = await client.post("/api/v1/agents/run", json={"goal": "hi"})
        assert resp.status_code == 403
    finally:
        get_settings().security.require_auth = None


# ─── 2. 默认口令 must_change_password ───────────────────────────────


async def test_default_admin_login_marks_must_change_password(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["must_change_password"] is True


async def test_change_password_clears_flag(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    token = resp.json()["access_token"]
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "admin", "new_password": "new-strong-pw-123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # 改密后再登录，标记应清除
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "new-strong-pw-123"},
    )
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False


# ─── 3. 登录限流 ────────────────────────────────────────────────────


async def test_login_rate_limit_lockout(client: AsyncClient) -> None:
    """1 分钟内 5 次失败 -> 第 6 次起 429 + retry_after。"""
    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "victim", "password": f"wrong-{i}"},
        )
        assert resp.status_code == 401, f"第 {i + 1} 次失败应 401"

    # 已锁定：即使密码正确也 429
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "victim", "password": "whatever"}
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    detail = resp.json()["detail"]
    assert detail["error"] == "login_locked"
    assert 0 < detail["retry_after"] <= 60


async def test_login_rate_limiter_is_per_username(client: AsyncClient) -> None:
    """锁定按 IP+用户名 隔离：victim 被锁不影响其他账号。"""
    for i in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"username": "victim", "password": f"wrong-{i}"},
        )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200


async def test_login_success_resets_counter(client: AsyncClient) -> None:
    """成功登录清零失败计数。"""
    for i in range(4):
        await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": f"wrong-{i}"},
        )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200
    # 计数已清零：再失败 4 次仍不应锁定
    for i in range(4):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": f"wrong-again-{i}"},
        )
        assert resp.status_code == 401


def test_login_rate_limiter_unit() -> None:
    """限流器单元测试：窗口滑动 + 锁定时长。"""
    from xagent.enterprise.auth.login_rate_limit import LoginRateLimiter

    limiter = LoginRateLimiter(max_failures=3, window_seconds=60, lockout_seconds=30)
    key = limiter.make_key("1.2.3.4", "Alice")
    assert key == "1.2.3.4:alice"  # 用户名大小写归一

    now = 1000.0
    assert limiter.record_failure(key, now) == 0.0
    assert limiter.record_failure(key, now + 1) == 0.0
    assert limiter.record_failure(key, now + 2) == 30.0  # 第 3 次触发锁定

    # 锁定起点为最后一次失败时刻（now+2），锁 30 秒
    assert limiter.locked_seconds(key, now + 10) == pytest.approx(22.0)
    assert limiter.locked_seconds(key, now + 33) == 0.0  # 锁定已过期

    # 成功后清零
    limiter.record_failure(key, now + 40)
    limiter.record_success(key)
    assert limiter.locked_seconds(key, now + 40) == 0.0
    assert limiter.record_failure(key, now + 41) == 0.0  # 重新从 1 计数


# ─── 4. shell 工具门禁 ──────────────────────────────────────────────


def test_shell_exec_not_registered_by_default() -> None:
    """默认 XAGENT_TOOLS__ENABLE_SHELL=false：shell_exec 不出现在注册表。"""
    from xagent.adapters.tools import get_tool_registry

    registry = get_tool_registry()
    assert registry.get("shell_exec") is None
    assert "shell_exec" not in registry.names()


def test_shell_exec_registered_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式开启后 shell_exec 注册可用。"""
    from xagent.adapters.tools import get_tool_registry, reset_tool_registry
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_TOOLS__ENABLE_SHELL", "true")
    get_settings.cache_clear()
    reset_tool_registry()
    try:
        registry = get_tool_registry()
        assert registry.get("shell_exec") is not None
    finally:
        reset_tool_registry()
        get_settings.cache_clear()


async def test_shell_exec_run_refuses_when_disabled() -> None:
    """即使被直接实例化调用，禁用时也返回明确错误（对 loop 透明）。"""
    from xagent.adapters.tools.base import ToolContext
    from xagent.adapters.tools.power_tools import ShellExecTool
    from xagent.enterprise.auth.principal import Principal

    tool = ShellExecTool()
    ctx = ToolContext(principal=Principal(user_id="u", tenant_id="t"))
    result = await tool.run({"command": "echo hi"}, ctx)
    assert result.ok is False
    assert "已被配置禁用" in (result.error or "")


# ─── 4b. python_exec 工具门禁 ────────────────────────────────────────


def test_python_exec_not_registered_by_default() -> None:
    """默认 XAGENT_TOOLS__ENABLE_PYTHON_EXEC=false：python_exec 不出现在注册表。"""
    from xagent.adapters.tools import get_tool_registry

    registry = get_tool_registry()
    assert registry.get("python_exec") is None
    assert "python_exec" not in registry.names()


def test_python_exec_registered_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式开启后 python_exec 注册可用。"""
    from xagent.adapters.tools import get_tool_registry, reset_tool_registry
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_TOOLS__ENABLE_PYTHON_EXEC", "true")
    get_settings.cache_clear()
    reset_tool_registry()
    try:
        registry = get_tool_registry()
        assert registry.get("python_exec") is not None
    finally:
        reset_tool_registry()
        get_settings.cache_clear()


async def test_python_exec_run_refuses_when_disabled() -> None:
    """即使被直接实例化调用，禁用时也返回明确错误（对 loop 透明）。"""
    from xagent.adapters.tools.base import ToolContext
    from xagent.adapters.tools.power_tools import PythonExecTool
    from xagent.enterprise.auth.principal import Principal

    tool = PythonExecTool()
    ctx = ToolContext(principal=Principal(user_id="u", tenant_id="t"))
    result = await tool.run({"code": "print('hi')"}, ctx)
    assert result.ok is False
    assert "已被配置禁用" in (result.error or "")


# ─── 5. 安全响应头 ──────────────────────────────────────────────────


async def test_security_headers_on_api_responses(client: AsyncClient) -> None:
    """业务端点响应（含 401）也应带安全头与 X-Request-ID。"""
    resp = await client.get("/api/v1/agents/roles")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("x-request-id")


async def test_request_id_echoed(client: AsyncClient) -> None:
    """客户端传入的 X-Request-ID 应原样回显。"""
    resp = await client.get("/health", headers={"X-Request-ID": "req-abc-123"})
    assert resp.headers.get("x-request-id") == "req-abc-123"
