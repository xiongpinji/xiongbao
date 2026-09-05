"""Atomic JSON persistence with owner-only file permissions."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path


def write_private_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        if os.name == "nt":
            _restrict_windows_file(temporary)
        assert descriptor is not None
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = None
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == "nt":
            _restrict_windows_file(path)
        else:
            path.chmod(0o600)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _restrict_windows_file(path: Path) -> None:
    identity = _get_windows_identity_unicode()
    if not _is_safe_windows_identity(identity):
        raise RuntimeError("failed to identify current user")
    system32 = _get_windows_system32()
    result = subprocess.run(  # noqa: S603 -- fixed System32 executable and argv
        [
            str(system32 / "icacls.exe"),
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{identity}:F",
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("failed to restrict private JSON permissions")


def _get_windows_system32() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise OSError("Windows system APIs are unavailable")
    length = windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if length <= 0 or length >= len(buffer):
        raise RuntimeError("failed to locate System32")
    system32 = Path(buffer.value)
    if not system32.is_absolute():
        raise RuntimeError("failed to locate System32")
    return system32


def _get_windows_identity_unicode() -> str:
    from ctypes import wintypes

    win_dll = getattr(ctypes, "WinDLL", None)
    win_error = getattr(ctypes, "WinError", None)
    get_last_error = getattr(ctypes, "get_last_error", None)
    if win_dll is None or win_error is None or get_last_error is None:
        raise OSError("Windows identity APIs are unavailable")
    name_sam_compatible = 2
    size = wintypes.ULONG(0)
    secur32 = win_dll("secur32", use_last_error=True)
    function = secur32.GetUserNameExW
    function.argtypes = [wintypes.ULONG, wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG)]
    function.restype = wintypes.BOOL
    function(name_sam_compatible, None, ctypes.byref(size))
    if size.value == 0:
        raise win_error(get_last_error())
    buffer = ctypes.create_unicode_buffer(size.value)
    if not function(name_sam_compatible, buffer, ctypes.byref(size)):
        raise win_error(get_last_error())
    return buffer.value.strip()


def _is_safe_windows_identity(identity: str) -> bool:
    normalized = identity.strip().lower()
    if not normalized or "\n" in identity or "\r" in identity or "\\" not in normalized:
        return False
    domain, user = normalized.split("\\", 1)
    if not domain or not user or user == "everyone":
        return False
    return domain not in {"builtin", "nt authority"}
