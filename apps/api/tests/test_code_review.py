"""Code Review 测试：diff 解析、AGENTS.md 规则注入、分级输出、API 端到端、CLI 冒烟。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.adapters.llm.base import LLMResponse, Message
from xagent.domains.code_review import (
    parse_unified_diff,
    reset_review_store,
    review_diff,
    run_review,
)
from xagent.domains.code_review.models import Finding, decide_verdict
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app

SAMPLE_DIFF = """\
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,5 +1,9 @@
 import os
+import subprocess
+
+def run(cmd):
+    return subprocess.call(cmd, shell=True)
+
 def main():
-    print("hello")
+    print("hello world")
     return 0
diff --git a/util.py b/util.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/util.py
@@ -0,0 +1,2 @@
+def add(a, b):
+    return a + b
"""


# ─── diff 解析 ───


def test_parse_unified_diff_files_and_counts() -> None:
    files = parse_unified_diff(SAMPLE_DIFF)
    assert [f.path for f in files] == ["app.py", "util.py"]
    app = files[0]
    assert app.additions == 6  # 6 行 '+'
    assert app.deletions == 1  # 1 行 '-'
    assert "subprocess" in app.patch


def test_parse_unified_diff_empty() -> None:
    assert parse_unified_diff("") == []
    assert parse_unified_diff("随便一段文本\n不是 diff") == []


# ─── verdict 分级 ───


def test_decide_verdict() -> None:
    assert decide_verdict([]) == "approve"
    assert decide_verdict([Finding(file="a", line=1, severity="low", issue="x")]) == "comment"
    assert decide_verdict([Finding(file="a", line=1, severity="high", issue="x")]) == (
        "request_changes"
    )
    # 非法 severity 归一为 info
    f = Finding(file="a", line=1, severity="weird", issue="x")
    assert f.severity == "info"


# ─── Fake LLM ───


class FakeReviewLLM:
    """按维度返回确定性 JSON 的伪 LLM；standards 维度在 prompt 含自定义规则时引用该规则。"""

    supports_tools = False

    def __init__(self, rule_trigger: str = "") -> None:
        self.rule_trigger = rule_trigger
        self.prompts: list[str] = []

    async def complete(
        self, messages: list[Message], **kwargs: Any
    ) -> LLMResponse:
        prompt = messages[-1].content
        self.prompts.append(prompt)
        if "总体摘要" in prompt:
            return LLMResponse(content="存在命令注入风险，建议修复后合并。", model="fake")
        findings: list[dict] = []
        if "逻辑正确性" in prompt:
            findings.append(
                {
                    "file": "app.py",
                    "line": 5,
                    "severity": "medium",
                    "issue": "run() 未处理非零退出码",
                    "suggestion": "检查返回值并抛出异常",
                }
            )
        elif "安全" in prompt:
            findings.append(
                {
                    "file": "app.py",
                    "line": 5,
                    "severity": "critical",
                    "issue": "subprocess shell=True 存在命令注入风险",
                    "suggestion": "使用参数列表并关闭 shell",
                }
            )
        elif "规范符合度" in prompt and self.rule_trigger and self.rule_trigger in prompt:
            findings.append(
                {
                    "file": "util.py",
                    "line": 1,
                    "severity": "low",
                    "issue": "新增函数缺少类型标注",
                    "suggestion": "补充类型标注",
                    "rule_ref": self.rule_trigger,
                }
            )
        return LLMResponse(content=json.dumps({"findings": findings}), model="fake")

    async def complete_with_tools(self, *a: Any, **k: Any) -> LLMResponse:
        raise NotImplementedError

    async def health(self) -> bool:
        return True


# ─── 服务层 ───


async def test_run_review_structured_output() -> None:
    result = await run_review(SAMPLE_DIFF, llm=FakeReviewLLM())
    assert result.status == "succeeded"
    assert result.verdict == "request_changes"  # 有 critical
    d = result.to_dict()
    assert d["stats"] == {"files_changed": 2, "additions": 8, "deletions": 1}
    assert d["severity_counts"] == {"critical": 1, "medium": 1}
    for f in d["findings"]:
        assert set(f) >= {"file", "line", "severity", "issue", "suggestion", "dimension"}
    assert set(result.dimensions) == {"logic", "security", "standards"}
    assert result.summary  # LLM 综合摘要


async def test_run_review_empty_diff_fails() -> None:
    result = await run_review("不是 diff", llm=FakeReviewLLM())
    assert result.status == "failed"
    assert result.error


async def test_agents_md_rule_injected_and_referenced(tmp_path) -> None:
    """给定仓库自定义规则时，standards 维度 prompt 应包含规则且 finding 引用该规则。"""
    rule = "所有公开函数必须带类型标注"
    (tmp_path / "AGENTS.md").write_text(f"# 项目规则\n- {rule}\n", encoding="utf-8")
    llm = FakeReviewLLM(rule_trigger=rule)

    result = await review_diff(diff=SAMPLE_DIFF, repo=str(tmp_path), llm=llm)

    assert result.instructions_applied is True
    assert any(rule in p for p in llm.prompts)  # 规则确实注入 prompt
    standards_findings = [f for f in result.findings if f.dimension == "standards"]
    assert standards_findings, "自定义规则应触发 standards finding"
    assert any(rule in f.rule_ref for f in standards_findings)


async def test_review_diff_repo_not_git_fails(tmp_path) -> None:
    with pytest.raises(ValueError, match="git"):
        await review_diff(repo=str(tmp_path), base="main", llm=FakeReviewLLM())


async def test_review_diff_requires_input() -> None:
    with pytest.raises(ValueError):
        await review_diff(llm=FakeReviewLLM())


# ─── API 端到端 ───


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_api_code_review_end_to_end(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    # lite 模式无 LLM key -> MockLLM 输出非 JSON -> 维度解析失败记 failed，
    # 但接口契约（review_id + 结构）必须成立
    resp = await client.post(
        "/api/v1/code-review", json={"diff": SAMPLE_DIFF}, headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_id"]
    assert body["status"] in {"succeeded", "partial", "failed"}
    result = body["result"]
    assert result["verdict"] in {"approve", "comment", "request_changes"}
    assert result["stats"]["files_changed"] == 2

    got = await client.get(f"/api/v1/code-review/{body['review_id']}", headers=_auth(token))
    assert got.status_code == 200
    assert got.json()["review_id"] == body["review_id"]


async def test_api_code_review_rbac_and_validation(client: AsyncClient) -> None:
    # viewer 只有 read，无 execute
    viewer = create_access_token(user_id="v", tenant_id="t1", roles=["viewer"])
    resp = await client.post(
        "/api/v1/code-review", json={"diff": SAMPLE_DIFF}, headers=_auth(viewer)
    )
    assert resp.status_code == 403

    # 匿名 401
    resp = await client.post("/api/v1/code-review", json={"diff": SAMPLE_DIFF})
    assert resp.status_code == 401

    # 缺 diff 且缺 repo+base -> 422
    member = create_access_token(user_id="m", tenant_id="t1", roles=["member"])
    resp = await client.post("/api/v1/code-review", json={}, headers=_auth(member))
    assert resp.status_code == 422


async def test_api_code_review_tenant_isolation(client: AsyncClient) -> None:
    reset_review_store()
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    resp = await client.post(
        "/api/v1/code-review", json={"diff": SAMPLE_DIFF}, headers=_auth(token_a)
    )
    rid = resp.json()["review_id"]
    got = await client.get(f"/api/v1/code-review/{rid}", headers=_auth(token_b))
    assert got.status_code == 404  # 跨租户不可见


# ─── CLI 冒烟 ───


def test_cli_review_smoke(tmp_path, capsys, monkeypatch) -> None:
    from xagent import cli
    from xagent.domains.code_review import service as review_service

    # 用 FakeReviewLLM 替换真实 LLM（get_llm_client 在 run_review 内部惰性调用）
    monkeypatch.setattr(
        review_service, "run_review",
        lambda diff_text, **kw: _fake_run(diff_text, **kw),
    )

    diff_file = tmp_path / "pr.diff"
    diff_file.write_text(SAMPLE_DIFF, encoding="utf-8")
    out_file = tmp_path / "review.md"
    rc = cli.main(
        ["review", "--repo", str(tmp_path), "--diff-file", str(diff_file),
         "--output", str(out_file)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Verdict: request_changes" in out
    assert "命令注入" in out
    assert "Findings" in out
    md = out_file.read_text(encoding="utf-8")
    assert "Verdict: request_changes" in md
    assert "| Severity |" in md


async def _fake_run(diff_text: str, **kw: Any):
    kw.pop("llm", None)
    return await run_review(diff_text, llm=FakeReviewLLM(), **kw)


def test_cli_review_bad_repo(tmp_path, capsys) -> None:
    from xagent import cli

    rc = cli.main(["review", "--repo", str(tmp_path), "--base", "main"])
    assert rc == 2
    assert "评审失败" in capsys.readouterr().err
