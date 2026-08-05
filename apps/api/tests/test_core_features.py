"""核心链路测试：工作流模板 / API Key / Skill 自动提炼 / Plan-and-Execute。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
async def client():
    from xagent.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture()
async def auth_headers(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ─── 工作流模板 CRUD ───


class TestWorkflowTemplates:
    @pytest.mark.anyio
    async def test_save_and_load_template(self, client: AsyncClient, auth_headers: dict):
        # 保存
        resp = await client.post(
            "/api/v1/workflows/templates/save",
            json={
                "name": "测试流程",
                "nodes": [{"id": "n1", "type": "wfAgent", "position": {"x": 0, "y": 0}, "data": {"kind": "agent", "label": "步骤1"}}],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        tpl = resp.json()["template"]
        assert tpl["name"] == "测试流程"
        assert tpl["version"] == 1
        tid = tpl["template_id"]

        # 加载
        resp2 = await client.get(f"/api/v1/workflows/templates/{tid}", headers=auth_headers)
        assert resp2.status_code == 200
        assert resp2.json()["template"]["name"] == "测试流程"

        # 列表
        resp3 = await client.get("/api/v1/workflows/templates/list", headers=auth_headers)
        assert resp3.status_code == 200
        assert resp3.json()["count"] >= 1

    @pytest.mark.anyio
    async def test_update_template_increments_version(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/workflows/templates/save",
            json={"name": "v1", "nodes": [], "edges": []},
            headers=auth_headers,
        )
        tid = resp.json()["template"]["template_id"]

        resp2 = await client.post(
            "/api/v1/workflows/templates/save",
            json={"name": "v2", "nodes": [], "edges": [], "template_id": tid},
            headers=auth_headers,
        )
        assert resp2.json()["template"]["version"] == 2
        assert resp2.json()["template"]["name"] == "v2"

    @pytest.mark.anyio
    async def test_delete_template(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/workflows/templates/save",
            json={"name": "to_delete", "nodes": [], "edges": []},
            headers=auth_headers,
        )
        tid = resp.json()["template"]["template_id"]

        resp2 = await client.delete(f"/api/v1/workflows/templates/{tid}", headers=auth_headers)
        assert resp2.status_code == 200

        resp3 = await client.get(f"/api/v1/workflows/templates/{tid}", headers=auth_headers)
        assert resp3.status_code == 404


# ─── API Key 管理 ───


class TestApiKeys:
    @pytest.mark.anyio
    async def test_create_and_list_key(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/tenants/api-keys",
            json={"name": "test-key", "scopes": ["*"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "raw_key" in data
        assert data["key"]["name"] == "test-key"

        # 列表
        resp2 = await client.get("/api/v1/tenants/api-keys", headers=auth_headers)
        assert resp2.json()["count"] >= 1

    @pytest.mark.anyio
    async def test_revoke_key(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/tenants/api-keys",
            json={"name": "revoke-me"},
            headers=auth_headers,
        )
        key_id = resp.json()["key"]["key_id"]

        resp2 = await client.post(f"/api/v1/tenants/api-keys/{key_id}/revoke", headers=auth_headers)
        assert resp2.status_code == 200

    @pytest.mark.anyio
    async def test_api_key_auth(self, client: AsyncClient, auth_headers: dict):
        # 创建 key
        resp = await client.post(
            "/api/v1/tenants/api-keys",
            json={"name": "auth-test", "scopes": ["*"]},
            headers=auth_headers,
        )
        raw_key = resp.json()["raw_key"]

        # 用 API Key 访问
        resp2 = await client.get(
            "/api/v1/tenants/info",
            headers={"X-API-Key": raw_key},
        )
        # API Key 认证应返回租户信息（member 角色可能无权限，但不应 401）
        assert resp2.status_code in (200, 403)


# ─── Skill 自动提炼 ───


class TestSkillAutoExtract:
    @pytest.mark.anyio
    async def test_extract_conditions(self):
        """测试 auto_extract 条件判断逻辑。"""
        from xagent.core.skills import get_skill_store

        store = get_skill_store()

        # 步数太少 → 不提炼
        result = await store.auto_extract(goal="简单任务", answer="完成", steps_count=1)
        assert result is None

        # 回答短且工具少 → 不提炼
        result2 = await store.auto_extract(goal="任务", answer="ok", steps_count=5, tools_used=["a"])
        assert result2 is None

    @pytest.mark.anyio
    async def test_extract_with_sufficient_content(self):
        """足够复杂时应触发提炼（规则模式，无 LLM）。"""
        from xagent.core.skills import get_skill_store

        store = get_skill_store()
        long_answer = "这是一段足够长的回答，包含了多个步骤的详细说明。" * 5
        result = await store.auto_extract(
            goal="创建项目结构并配置环境",
            answer=long_answer,
            steps_count=6,
            tools_used=["filesystem", "shell", "editor"],
        )
        # 无 LLM 时应走规则提取路径
        assert result is not None
        assert result.name != ""


# ─── Plan-and-Execute ───


class TestPlanExecute:
    def test_plan_step_model(self):
        from xagent.core.orchestration.plan_execute import PlanStep

        step = PlanStep(id=1, description="创建目录", tool_hint="filesystem")
        assert step.status == "pending"
        assert step.depends_on == []

    def test_execution_plan_model(self):
        from xagent.core.orchestration.plan_execute import ExecutionPlan, PlanStep

        plan = ExecutionPlan(
            goal="测试目标",
            steps=[
                PlanStep(id=1, description="步骤1"),
                PlanStep(id=2, description="步骤2", depends_on=[1]),
            ],
        )
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == [1]

    def test_ready_steps(self):
        from xagent.core.orchestration.plan_execute import ExecutionPlan, PlanStep

        plan = ExecutionPlan(
            goal="测试",
            steps=[
                PlanStep(id=1, description="A"),
                PlanStep(id=2, description="B", depends_on=[1]),
                PlanStep(id=3, description="C"),
            ],
        )
        ready = plan.ready_steps
        # 步骤 1 和 3 无依赖，应就绪
        assert len(ready) == 2
        assert {s.id for s in ready} == {1, 3}


# ─── 租户管理 ───


class TestTenantManagement:
    @pytest.mark.anyio
    async def test_tenant_info(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/tenants/info", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tenant_id" in data
        assert "roles_available" in data

    @pytest.mark.anyio
    async def test_create_and_delete_user(self, client: AsyncClient, auth_headers: dict):
        # 创建
        resp = await client.post(
            "/api/v1/tenants/users",
            json={"username": "testuser123", "password": "pass123456", "roles": ["member"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        user_id = resp.json()["user_id"]

        # 删除
        resp2 = await client.delete(f"/api/v1/tenants/users/{user_id}", headers=auth_headers)
        assert resp2.status_code == 200
