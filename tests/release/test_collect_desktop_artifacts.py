from pathlib import Path

import pytest

from scripts import collect_desktop_artifacts as collector


@pytest.fixture(autouse=True)
def _unsigned_signature_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "_inspect_signature", lambda _path: "unsigned")


def _write_installers(root: Path) -> None:
    (root / "msi").mkdir(parents=True)
    (root / "nsis").mkdir(parents=True)
    (root / "msi" / "X-Agent_1.1.3_x64_en-US.msi").write_bytes(b"msi")
    (root / "nsis" / "X-Agent_1.1.3_x64-setup.exe").write_bytes(b"nsis")


def test_collect_records_hash_size_arch_and_unsigned_state(tmp_path: Path) -> None:
    _write_installers(tmp_path)

    manifest = collector.collect_artifacts(
        tmp_path,
        source_sha="a" * 40,
        version="1.1.3",
    )

    assert manifest["source_sha"] == "a" * 40
    assert manifest["version"] == "1.1.3"
    assert manifest["classification"] == "unsigned_local_candidate"
    assert {item["format"] for item in manifest["artifacts"]} == {"nsis", "msi"}
    assert all(item["arch"] == "x64" for item in manifest["artifacts"])
    assert all(
        len(item["sha256"]) == 64 and item["size_bytes"] > 0
        for item in manifest["artifacts"]
    )
    assert all(item["signature"] == "unsigned" for item in manifest["artifacts"])


@pytest.mark.parametrize("source_sha", ["A" * 40, "a" * 39, "../escape"])
def test_collect_rejects_invalid_source_sha(tmp_path: Path, source_sha: str) -> None:
    _write_installers(tmp_path)

    with pytest.raises(ValueError, match="source SHA"):
        collector.collect_artifacts(
            tmp_path,
            source_sha=source_sha,
            version="1.1.3",
        )


def test_collect_rejects_missing_duplicate_empty_or_wrong_version(
    tmp_path: Path,
) -> None:
    _write_installers(tmp_path)
    (tmp_path / "nsis" / "X-Agent_1.1.3_x64-setup.exe").write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        collector.collect_artifacts(
            tmp_path,
            source_sha="b" * 40,
            version="1.1.3",
        )

    (tmp_path / "nsis" / "X-Agent_1.1.3_x64-setup.exe").unlink()
    with pytest.raises(ValueError, match="exactly one NSIS"):
        collector.collect_artifacts(
            tmp_path,
            source_sha="b" * 40,
            version="1.1.3",
        )

    (tmp_path / "nsis" / "X-Agent_2.0.0_x64-setup.exe").write_bytes(b"nsis")
    with pytest.raises(ValueError, match="version"):
        collector.collect_artifacts(
            tmp_path,
            source_sha="b" * 40,
            version="1.1.3",
        )
