"""鉴权与授权测试：JWT、Principal、RBAC、越权防护。"""

from __future__ import annotations

import pytest
from xagent.enterprise.auth import create_access_token, decode_token
from xagent.enterprise.auth.jwt_auth import InvalidTokenError
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.rbac import AccessRequest, authorize


def test_jwt_roundtrip() -> None:
    token = create_access_token(
        user_id="u1", tenant_id="t1", roles=["member"], scopes=["s"]
    )
    p = decode_token(token)
    assert p.user_id == "u1"
    assert p.tenant_id == "t1"
    assert "member" in p.roles


def test_jwt_rejects_tampered() -> None:
    token = create_access_token(user_id="u1", tenant_id="t1")
    with pytest.raises(InvalidTokenError):
        decode_token(token + "tampered")


def test_rbac_admin_all() -> None:
    admin = Principal(user_id="a", tenant_id="t1", roles=frozenset({"admin"}))
    assert authorize(admin, AccessRequest("billing", "manage"))
    assert authorize(admin, AccessRequest("agent", "execute"))


def test_rbac_member_limited() -> None:
    member = Principal(user_id="m", tenant_id="t1", roles=frozenset({"member"}))
    assert authorize(member, AccessRequest("agent", "execute"))
    assert authorize(member, AccessRequest("memory", "write"))
    # member 不能管理计费
    assert not authorize(member, AccessRequest("billing", "manage"))


def test_rbac_viewer_readonly() -> None:
    viewer = Principal(user_id="v", tenant_id="t1", roles=frozenset({"viewer"}))
    assert authorize(viewer, AccessRequest("memory", "read"))
    assert not authorize(viewer, AccessRequest("memory", "write"))


def test_principal_anonymous_has_tenant() -> None:
    anon = Principal.anonymous()
    assert anon.tenant_id  # 匿名也必有租户
    assert anon.is_anonymous
