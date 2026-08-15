from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from xagent.domains.creative_studio.delivery_bundle import build_delivery_bundle


def sample_production(
    *,
    image_outputs: list[str] | None = None,
    audio_outputs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "storyboard_id": "storyboard-test",
        "status": "produced",
        "timeline_id": "timeline-test",
        "timeline": {"id": "timeline-test", "clips": []},
        "shots": [
            {
                "shot_id": "shot-1",
                "image_outputs": image_outputs or [],
                "video_outputs": [],
                "audio_outputs": audio_outputs or [],
            }
        ],
        "failures": [],
    }


def test_build_bundle_contains_manifest_timeline_and_allowed_media(
    tmp_path: Path,
) -> None:
    media = tmp_path / "media" / "voice.wav"
    media.parent.mkdir()
    media.write_bytes(b"RIFF-test-audio")
    payload = build_delivery_bundle(
        sample_production(audio_outputs=[str(media)]),
        allowed_roots=(tmp_path,),
    )

    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        asset_name = f"assets/{hashlib.sha256(media.read_bytes()).hexdigest()[:12]}-voice.wav"
        assert {"manifest.json", "production.json", "timeline.json", asset_name} <= names
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        entry = next(item for item in manifest["files"] if item["path"] == asset_name)
        assert entry["sha256"] == hashlib.sha256(b"RIFF-test-audio").hexdigest()
        assert entry["size_bytes"] == len(b"RIFF-test-audio")
        for member in manifest["files"]:
            member_bytes = archive.read(member["path"])
            assert hashlib.sha256(member_bytes).hexdigest() == member["sha256"]
            assert len(member_bytes) == member["size_bytes"]


def test_build_bundle_never_reads_outside_allowed_roots(tmp_path: Path) -> None:
    outside = tmp_path.parent / "private.txt"
    outside.write_text("must-not-leak", encoding="utf-8")
    payload = build_delivery_bundle(
        sample_production(audio_outputs=[str(outside)]),
        allowed_roots=(tmp_path,),
    )

    with ZipFile(BytesIO(payload)) as archive:
        contents = b"".join(archive.read(name) for name in archive.namelist())
        assert b"must-not-leak" not in contents
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["references"][0]["classification"] == "outside_allowed_roots"


def test_placeholder_is_declared_as_fixture_not_real_media() -> None:
    payload = build_delivery_bundle(
        sample_production(image_outputs=["placeholder://image/task-1"]),
        allowed_roots=(),
    )

    with ZipFile(BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["provider_classification"] == "fixture_local"
        assert manifest["external_provider_acceptance"] == "not_authorized"
        assert manifest["references"][0]["classification"] == "placeholder_fixture"
        assert not any(name.startswith("assets/") for name in archive.namelist())


def test_bundle_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    media = tmp_path / "voice.wav"
    media.write_bytes(b"RIFF-deterministic")
    production = sample_production(audio_outputs=[str(media)])

    first = build_delivery_bundle(production, allowed_roots=(tmp_path,))
    second = build_delivery_bundle(production, allowed_roots=(tmp_path,))

    assert first == second
