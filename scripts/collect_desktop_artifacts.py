"""Collect and verify Windows desktop installer artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_SOURCE_SHA = re.compile(r"^[a-f0-9]{40}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")


def _inspect_signature(path: Path) -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if os.name != "nt" or shell is None:
        raise RuntimeError(
            "Authenticode signature inspection requires Windows PowerShell"
        )
    env = {**os.environ, "XAGENT_ARTIFACT_PATH": str(path)}
    script = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
        "(Get-AuthenticodeSignature -LiteralPath $env:XAGENT_ARTIFACT_PATH).Status.ToString()"
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    if result.returncode != 0:
        raise ValueError(f"signature inspection failed for {path.name}")
    status = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if status == "NotSigned":
        return "unsigned"
    if status == "Valid":
        return "valid"
    raise ValueError(f"invalid Authenticode signature for {path.name}: {status}")


def _artifact_entry(
    path: Path, root: Path, version: str, format_name: str
) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"installer is not a regular file: {path.name}")
    if path.stat().st_size <= 0:
        raise ValueError(f"installer is empty: {path.name}")
    lowered = path.name.lower()
    if f"_{version.lower()}_" not in lowered:
        raise ValueError(f"installer version does not match {version}: {path.name}")
    if "_x64" not in lowered:
        raise ValueError(f"installer architecture is not x64: {path.name}")
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "format": format_name,
        "version": version,
        "arch": "x64",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "signature": _inspect_signature(path),
    }


def collect_artifacts(
    bundle_root: Path,
    *,
    source_sha: str,
    version: str,
) -> dict[str, object]:
    if _SOURCE_SHA.fullmatch(source_sha) is None:
        raise ValueError("source SHA must be 40 lowercase hexadecimal characters")
    if _VERSION.fullmatch(version) is None:
        raise ValueError("invalid product version")
    root = Path(bundle_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("bundle root must be a directory")
    msi_files = sorted(root.rglob("*.msi"))
    nsis_files = sorted(root.rglob("*-setup.exe"))
    if len(msi_files) != 1:
        raise ValueError(f"expected exactly one MSI installer, found {len(msi_files)}")
    if len(nsis_files) != 1:
        raise ValueError(
            f"expected exactly one NSIS installer, found {len(nsis_files)}"
        )

    artifacts = [
        _artifact_entry(msi_files[0], root, version, "msi"),
        _artifact_entry(nsis_files[0], root, version, "nsis"),
    ]
    signatures = {str(item["signature"]) for item in artifacts}
    if signatures == {"unsigned"}:
        classification = "unsigned_local_candidate"
    elif signatures == {"valid"}:
        classification = "signed_candidate"
    else:
        raise ValueError("installer signatures are inconsistent")
    return {
        "schema_version": "1.0",
        "source_sha": source_sha,
        "version": version,
        "classification": classification,
        "artifacts": artifacts,
    }


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = collect_artifacts(
        args.bundle_root,
        source_sha=args.source_sha,
        version=args.version,
    )
    _write_json_atomic(args.output, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
