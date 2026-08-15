from pathlib import Path

from xagent.adapters.storage.base import LocalObjectStore
from xagent.core.scheduler import Scheduler
from xagent.core.skills import SkillStore, default_skills_root
from xagent.core.workflow_templates import WorkflowTemplateStore
from xagent.domains.skill_packages.service import default_packages_root
from xagent.infra.paths import data_dir, data_path
from xagent.infra.settings import MediaSettings, RecoverySettings


def test_runtime_data_dir_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runtime-data"
    monkeypatch.setenv("XAGENT_DATA_DIR", str(root))

    assert data_dir() == root
    assert data_path("scheduler") == root / "scheduler"


def test_file_stores_use_runtime_data_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runtime-data"
    monkeypatch.setenv("XAGENT_DATA_DIR", str(root))

    scheduler = Scheduler()
    templates = WorkflowTemplateStore()

    assert scheduler._dir == root / "scheduler"
    assert templates._dir == root / "workflow_templates"


def test_default_runtime_outputs_share_data_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runtime-data"
    monkeypatch.setenv("XAGENT_DATA_DIR", str(root))
    monkeypatch.delenv("XAGENT_SKILLS_ROOT", raising=False)
    monkeypatch.delenv("XAGENT_SKILL_PACKAGES_ROOT", raising=False)

    assert default_skills_root() == root / "skills"
    assert default_packages_root() == root / "skill-packages"
    assert LocalObjectStore()._root == root / "storage"
    assert MediaSettings().tts_output_dir == str(root / "tts")
    assert RecoverySettings().evidence_output_dir == str(root / "recovery-evidence")


def test_skill_store_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "skills"
    monkeypatch.setenv("XAGENT_SKILLS_ROOT", str(root))
    store = SkillStore()
    assert store._dir == root


def test_skill_package_root_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "skill-packages"
    monkeypatch.setenv("XAGENT_SKILL_PACKAGES_ROOT", str(root))
    assert default_packages_root() == root
