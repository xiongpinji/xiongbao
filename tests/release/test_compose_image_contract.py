from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_commercial_compose_dependencies_use_digests() -> None:
    for relative in ("docker-compose.yml", "deploy/compose/docker-compose.yml"):
        compose = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
        images = {
            name: service["image"]
            for name, service in compose["services"].items()
            if "image" in service
        }
        assert images, relative
        for service, image in images.items():
            assert "@sha256:" in image, f"{relative}:{service}={image}"
            assert "latest" not in image, f"{relative}:{service}={image}"


def test_helm_dependency_images_use_digests() -> None:
    values = yaml.safe_load((ROOT / "deploy/helm/values.yaml").read_text(encoding="utf-8"))

    for dependency in ("postgres", "redis", "qdrant"):
        assert "@sha256:" in values[dependency]["image"], dependency
