"""AGENTS.md 分层指令测试（对标 Codex 三层合并：用户级 < 工作区根 < 子目录级）。"""

from __future__ import annotations

from xagent.core.instructions import get_layered_instructions, load_layers


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
        assert [l.level for l in layers] == ["subdir"]
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
        assert all(l.level != "subdir" for l in layers)

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
