"""AGENTS.md 分层指令测试（对标 Codex 三层合并：用户级 < 工作区根 < 子目录级）。"""

from __future__ import annotations

from xagent.core.instructions import (
    extract_task_paths,
    get_layered_instructions,
    load_layers,
)


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestLayeredInstructions:
    def test_empty_workspace_returns_empty(self, tmp_path):
        assert get_layered_instructions(tmp_path, user_dir=tmp_path / "nohome") == ""

    def test_workspace_root_only(self, tmp_path):
        _write(tmp_path / "AGENTS.md", "工作区根指令")
        out = get_layered_instructions(tmp_path, user_dir=tmp_path / "nohome")
        assert "工作区根指令" in out
        assert "工作区根" in out

    def test_three_layers_priority_order(self, tmp_path):
        """三层合并：用户级在最前（优先级低），子目录级在最后（优先级高）。"""
        ws = tmp_path / "ws"
        user = tmp_path / "userhome"
        _write(user / "AGENTS.md", "USER-RULE")
        _write(ws / "AGENTS.md", "WS-RULE")
        _write(ws / "apps" / "api" / "AGENTS.md", "SUBDIR-RULE")

        out = get_layered_instructions(ws, task_paths=["apps/api"], user_dir=user)
        i_user = out.index("USER-RULE")
        i_ws = out.index("WS-RULE")
        i_sub = out.index("SUBDIR-RULE")
        assert i_user < i_ws < i_sub
        # 覆盖规则说明
        assert "优先级从低到高" in out

    def test_subdir_nearest_wins_ordering(self, tmp_path):
        """多个子目录层：越深的目录越靠后（优先级越高）。"""
        ws = tmp_path / "ws"
        _write(ws / "apps" / "AGENTS.md", "APPS-RULE")
        _write(ws / "apps" / "api" / "AGENTS.md", "API-RULE")
        out = get_layered_instructions(
            ws, task_paths=["apps/api/main.py"], user_dir=tmp_path / "nohome",
        )
        assert out.index("APPS-RULE") < out.index("API-RULE")

    def test_task_path_file_uses_parent_dir(self, tmp_path):
        """任务路径指向文件时，取其所在目录的就近指令。"""
        ws = tmp_path / "ws"
        _write(ws / "src" / "AGENTS.md", "SRC-RULE")
        layers = load_layers(ws, task_paths=["src/mod/x.py"], user_dir=tmp_path / "nohome")
        assert [layer.level for layer in layers] == ["subdir"]
        assert layers[0].content == "SRC-RULE"

    def test_path_outside_workspace_ignored(self, tmp_path):
        """越出工作区的任务路径不泄漏外部 AGENTS.md。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write(tmp_path / "AGENTS.md", "OUTSIDE-RULE")
        # ../ 解析到工作区外 → 不收集任何子目录层
        out = get_layered_instructions(ws, task_paths=["../"], user_dir=tmp_path / "nohome")
        assert "OUTSIDE-RULE" not in out
        layers = load_layers(ws, task_paths=["../../etc"], user_dir=tmp_path / "nohome")
        assert all(layer.level != "subdir" for layer in layers)

    def test_missing_layers_skipped(self, tmp_path):
        """缺层时跳过，不报错。"""
        ws = tmp_path / "ws"
        _write(ws / "AGENTS.md", "WS-ONLY")
        out = get_layered_instructions(ws, task_paths=["no/such/dir"], user_dir=tmp_path / "nohome")
        assert "WS-ONLY" in out

    def test_default_user_dir_env(self, tmp_path, monkeypatch):
        """XAGENT_USER_HOME 可覆盖用户级目录。"""
        home = tmp_path / "custom_home"
        _write(home / "AGENTS.md", "ENV-USER-RULE")
        monkeypatch.setenv("XAGENT_USER_HOME", str(home))
        ws = tmp_path / "ws"
        ws.mkdir()
        out = get_layered_instructions(ws)
        assert "ENV-USER-RULE" in out

    def test_total_cap(self, tmp_path):
        """合并总量有上限，防止超长注入。"""
        ws = tmp_path / "ws"
        _write(ws / "AGENTS.md", "x" * 2900)
        _write(ws / "a" / "AGENTS.md", "y" * 2900)
        _write(ws / "a" / "b" / "AGENTS.md", "z" * 2900)
        out = get_layered_instructions(ws, task_paths=["a/b"], user_dir=tmp_path / "nohome")
        assert len(out) <= 6200  # _TOTAL_MAX_CHARS + 覆盖说明


class _Msg:
    """模拟带原生工具调用的历史消息。"""

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class TestExtractTaskPaths:
    """[工作流S3-2] 任务路径识别：goal 显式路径优先，历史工具调用次之，越界不读取。"""

    def test_goal_relative_path_extracted(self, tmp_path):
        ws = tmp_path / "ws"
        _write(ws / "src" / "foo.py", "x = 1\n")
        _write(ws / "docs" / "bar" / "readme.md", "# bar\n")
        out = extract_task_paths(ws, goal="请修改 src/foo.py 并更新 docs/bar/ 下的文档")
        assert out == ["src/foo.py", "docs/bar"]

    def test_goal_no_path_returns_none(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        assert extract_task_paths(ws, goal="帮我写一个排序算法") is None

    def test_goal_nonexistent_path_filtered(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        assert extract_task_paths(ws, goal="看看 src/ghost.py 有没有问题") is None

    def test_goal_outside_workspace_rejected(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        _write(tmp_path / "secret.py", "s = 1\n")
        # ../ 与绝对路径一律拒绝
        assert extract_task_paths(ws, goal="读取 ../secret.py") is None
        assert extract_task_paths(ws, goal=f"读取 {tmp_path.as_posix()}/secret.py") is None

    def test_history_tool_call_path_fallback(self, tmp_path):
        ws = tmp_path / "ws"
        _write(ws / "apps" / "api" / "main.py", "pass\n")
        history = [_Msg([{
            "id": "c1", "type": "function",
            "function": {"name": "file_read", "arguments": '{"path": "apps/api/main.py"}'},
        }])]
        out = extract_task_paths(ws, goal="继续刚才的修改", history=history)
        assert out == ["apps/api/main.py"]

    def test_goal_beats_history_priority(self, tmp_path):
        ws = tmp_path / "ws"
        _write(ws / "a" / "x.py", "\n")
        _write(ws / "b" / "y.py", "\n")
        history = [_Msg([{"function": {"name": "file_read", "arguments": '{"path": "b/y.py"}'}}])]
        out = extract_task_paths(ws, goal="改 a/x.py", history=history)
        assert out == ["a/x.py", "b/y.py"]

    def test_end_to_end_subdir_layer_via_goal(self, tmp_path):
        """goal 含子路径 → 子目录层生效且按就近优先（深的靠后）。"""
        ws = tmp_path / "ws"
        _write(ws / "AGENTS.md", "WS-RULE")
        _write(ws / "apps" / "AGENTS.md", "APPS-RULE")
        _write(ws / "apps" / "api" / "AGENTS.md", "API-RULE")
        _write(ws / "apps" / "api" / "main.py", "pass\n")
        goal = "重构 apps/api/main.py 的启动逻辑"
        paths = extract_task_paths(ws, goal=goal)
        out = get_layered_instructions(ws, task_paths=paths, user_dir=tmp_path / "nohome")
        assert out.index("WS-RULE") < out.index("APPS-RULE") < out.index("API-RULE")

    def test_end_to_end_no_goal_path_keeps_two_layers(self, tmp_path):
        """goal 无路径 → task_paths 为 None，子目录层不生效（保持现状行为）。"""
        ws = tmp_path / "ws"
        _write(ws / "AGENTS.md", "WS-RULE")
        _write(ws / "sub" / "AGENTS.md", "SUB-RULE")
        paths = extract_task_paths(ws, goal="随便聊聊")
        assert paths is None
        out = get_layered_instructions(ws, task_paths=paths, user_dir=tmp_path / "nohome")
        assert "WS-RULE" in out
        assert "SUB-RULE" not in out
