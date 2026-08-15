from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest
from xagent.infra.secure_json import write_private_json


def test_write_private_json_is_atomic_and_private(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "config.json"

    write_private_json(target, {"model": "ollama/qwen3:4b"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "model": "ollama/qwen3:4b"
    }
    assert target.read_bytes().endswith(b"\n")
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


def test_write_private_json_replaces_existing_document(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text('{"old": true}\n', encoding="utf-8")

    write_private_json(target, {"new": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert "old" not in target.read_text(encoding="utf-8")


def test_write_private_json_removes_partial_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "config.json"

    with pytest.raises(TypeError):
        write_private_json(target, {"invalid": object()})

    assert not target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL contract")
def test_write_private_json_restricts_windows_acl_to_unicode_identity(
    tmp_path: Path,
) -> None:
    target = tmp_path / "config.json"
    completed = mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch(
        "xagent.infra.secure_json._get_windows_identity_unicode",
        return_value="峰哥工作站\\canqu",
    ), mock.patch(
        "xagent.infra.secure_json.subprocess.run",
        return_value=completed,
    ) as subprocess_run:
        write_private_json(target, {"safe": True})

    commands = [call.args[0] for call in subprocess_run.call_args_list]
    assert len(commands) == 2
    assert all(command[0].lower().endswith("icacls.exe") for command in commands)
    assert all("峰哥工作站\\canqu:F" in command for command in commands)
    assert all("Everyone:F" not in command for command in commands)
