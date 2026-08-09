from pathlib import Path

from xagent.core.skills import SkillStore
from xagent.domains.skill_packages.service import default_packages_root


def test_skill_store_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "skills"
    monkeypatch.setenv("XAGENT_SKILLS_ROOT", str(root))
    store = SkillStore()
    assert store._dir == root


def test_skill_package_root_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "skill-packages"
    monkeypatch.setenv("XAGENT_SKILL_PACKAGES_ROOT", str(root))
    assert default_packages_root() == root
