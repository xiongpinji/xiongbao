from __future__ import annotations

import argparse
import ctypes
import json
import os
import secrets
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
GENERATED_KEYS = (
    "POSTGRES_PASSWORD",
    "XAGENT_SECURITY__JWT_SECRET",
    "XAGENT_PLATFORM_MCP_TOKEN",
    "GRAFANA_ADMIN_PASSWORD",
)
PORTS = {
    "XAGENT_POSTGRES_PORT": ("postgres", "5432"),
    "XAGENT_REDIS_PORT": ("redis", "6379"),
    "XAGENT_QDRANT_HTTP_PORT": ("qdrant", "6333"),
    "XAGENT_QDRANT_GRPC_PORT": ("qdrant", "6334"),
    "XAGENT_API_PORT": ("api", "8000"),
    "XAGENT_WEB_PORT": ("web", "80"),
    "XAGENT_CONTEXTFORGE_PORT": ("contextforge", "8080"),
    "XAGENT_OPENFGA_PORT": ("openfga", "8081"),
    "XAGENT_LITELLM_PORT": ("litellm", "4000"),
    "XAGENT_LANGFUSE_PORT": ("langfuse", "3000"),
    "XAGENT_MCP_PORT": ("platform-mcp", "8100"),
    "XAGENT_PROMETHEUS_PORT": ("prometheus", "9090"),
    "XAGENT_GRAFANA_PORT": ("grafana", "3000"),
}
COMMAND_TIMEOUT_SECONDS = 60


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def init_env(template: Path, target: Path) -> None:
    text = template.read_text(encoding="utf-8")
    for key in GENERATED_KEYS:
        text = text.replace(f"{key}=__GENERATE__", f"{key}={secrets.token_urlsafe(36)}")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\r\n", "\n").encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd: int | None = None
    created = False
    try:
        fd = os.open(str(target), flags, 0o600)
        created = True
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        restrict_env_permissions(target)
    except FileExistsError:
        raise
    except Exception:
        if fd is not None:
            os.close(fd)
        if created:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        raise


def restrict_env_permissions(path: Path) -> None:
    if os.name == "nt":
        system32 = get_windows_system32()
        account = get_windows_identity(system32)
        result = subprocess.run(
            [str(system32 / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"{account}:F"],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("failed to restrict env file permissions")
        return
    path.chmod(0o600)
    if path.stat().st_mode & 0o777 != 0o600:
        raise RuntimeError("failed to restrict env file permissions")


def get_windows_system32() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if length <= 0 or length >= len(buffer):
        raise RuntimeError("failed to locate System32")
    system32 = Path(buffer.value)
    if not system32.is_absolute():
        raise RuntimeError("failed to locate System32")
    return system32


def get_windows_identity(system32: Path) -> str:
    result = subprocess.run(
        [str(system32 / "whoami.exe")],
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("failed to identify current user")
    stdout = result.stdout
    if isinstance(stdout, bytes):
        # whoami.exe 按控制台 OEM 代码页输出（中文 Windows 为 GBK/cp936），
        # 不能按 UTF-8 解码，否则非 ASCII 机器名/用户名乱码导致 icacls 1332。
        stdout = stdout.decode(_console_codepage(), errors="replace")
    identity = stdout.strip()
    if not is_safe_windows_identity(identity):
        raise RuntimeError("failed to identify current user")
    return identity


def _console_codepage() -> str:
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return "utf-8"
    oemcp = windll.kernel32.GetOEMCP()
    return f"cp{oemcp}" if oemcp else "utf-8"


def is_safe_windows_identity(identity: str) -> bool:
    normalized = identity.strip().lower()
    if not normalized or "\n" in identity or "\r" in identity:
        return False
    if "\\" not in normalized:
        return False
    domain, user = normalized.split("\\", 1)
    if not domain or not user:
        return False
    if user == "everyone" or normalized == "everyone":
        return False
    if domain in {"builtin", "nt authority"}:
        return False
    return True


def validate_env(values: dict[str, str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if values.get("POSTGRES_PASSWORD", "").lower() in {"", "xagent", "password", "__generate__"}:
        errors.append({"code": "weak_postgres_password", "message": "PostgreSQL password is not strong"})
    if len(values.get("XAGENT_SECURITY__JWT_SECRET", "")) < 32:
        errors.append({"code": "weak_jwt_secret", "message": "JWT secret must contain at least 32 characters"})
    if len(values.get("XAGENT_PLATFORM_MCP_TOKEN", "")) < 32:
        errors.append({"code": "weak_mcp_token", "message": "Platform MCP token must contain at least 32 characters"})
    if len(values.get("GRAFANA_ADMIN_PASSWORD", "")) < 16:
        errors.append({"code": "weak_grafana_password", "message": "Grafana password must contain at least 16 characters"})
    if values.get("XAGENT_SECURITY__REQUIRE_AUTH", "").lower() != "true":
        errors.append({"code": "auth_disabled", "message": "Full mode requires authentication"})
    if "*" in values.get("XAGENT_CORS_ORIGINS", ""):
        errors.append({"code": "wildcard_cors", "message": "Wildcard CORS is forbidden"})
    if not values.get("XAGENT_LLM__OLLAMA_MODEL", "").strip():
        errors.append({"code": "missing_ollama_model", "message": "Ollama model is required"})
    return errors


def run_command(command: Sequence[str]) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", "command timed out")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def check_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def fetch_ollama_models() -> set[str]:
    with urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {item.get("name", "") for item in payload.get("models", [])}


def write_report(output: Path, report: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_report(checks: list[dict[str, object]], branch: str = "", commit: str = "") -> dict[str, object]:
    return {
        "ok": all(bool(check["ok"]) for check in checks),
        "time": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "commit": commit,
        "checks": checks,
    }


def add_check(checks: list[dict[str, object]], name: str, ok: bool, detail: str) -> bool:
    checks.append({"name": name, "ok": ok, "detail": detail})
    return ok


def check_git(checks: list[dict[str, object]], expected_branch: str) -> tuple[bool, str, str]:
    branch_result = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    status_result = run_command(["git", "status", "--porcelain"])
    commit_result = run_command(["git", "rev-parse", "HEAD"])
    branch = branch_result.stdout.strip()
    commit = commit_result.stdout.strip()
    if branch_result.returncode != 0 or status_result.returncode != 0 or commit_result.returncode != 0:
        return add_check(checks, "git", False, "git command failed"), branch, commit
    if branch != expected_branch:
        return add_check(checks, "git", False, f"branch mismatch: {branch}"), branch, commit
    if status_result.stdout.strip():
        return add_check(checks, "git", False, "working tree is not clean"), branch, commit
    return add_check(checks, "git", True, f"branch {branch} clean"), branch, commit


def check_command(checks: list[dict[str, object]], name: str, command: Sequence[str]) -> bool:
    result = run_command(command)
    if result.returncode != 0:
        if result.returncode == 124:
            return add_check(checks, name, False, "command_timed_out")
        return add_check(checks, name, False, f"command_failed:{result.returncode}")
    return add_check(checks, name, True, "ok")


def parse_port_mapping(stdout: str) -> tuple[str, int] | None:
    text = stdout.strip()
    if not text:
        return None
    host_port = text.rsplit(":", 1)
    if len(host_port) != 2:
        return None
    try:
        return host_port[0].strip("[]"), int(host_port[1])
    except ValueError:
        return None


def normalize_loopback(host: str) -> str | None:
    value = host.strip().lower()
    if value in {"127.0.0.1", "localhost", "::1"}:
        return "127.0.0.1"
    return None


def same_project_owns_port(
    env_file: Path,
    compose_file: Path,
    project_name: str,
    service: str,
    container_port: str,
    expected_port: int,
    expected_host: str,
) -> bool:
    expected_loopback = normalize_loopback(expected_host)
    if expected_loopback is None:
        return False
    result = run_command([
        "docker", "compose", "--env-file", str(env_file),
        "-f", str(compose_file), "-p", project_name, "port", service, container_port,
    ])
    if result.returncode != 0:
        return False
    mapping = parse_port_mapping(result.stdout)
    if mapping is None:
        return False
    host, published_port = mapping
    return (
        normalize_loopback(host) == expected_loopback
        and published_port == expected_port
    )


def check_ports(
    checks: list[dict[str, object]],
    values: dict[str, str],
    env_file: Path,
    compose_file: Path,
    project_name: str,
    allow_running_project: bool,
) -> bool:
    host = values.get("XAGENT_BIND_ADDRESS", "127.0.0.1")
    if normalize_loopback(host) is None:
        return add_check(checks, "ports", False, "invalid_bind_address")
    checked = 0
    occupied: list[str] = []
    for key, (service, container_port) in PORTS.items():
        raw = values.get(key)
        if not raw:
            continue
        try:
            port = int(raw)
        except ValueError:
            occupied.append(f"{key}:invalid")
            continue
        checked += 1
        if check_port_available(host, port):
            continue
        if allow_running_project and same_project_owns_port(
            env_file, compose_file, project_name, service, container_port, port, host
        ):
            continue
        occupied.append(key)
    if occupied:
        return add_check(checks, "ports", False, "unavailable_port_keys:" + ",".join(occupied))
    return add_check(checks, "ports", True, f"checked:{checked}")


def check_ollama(checks: list[dict[str, object]], model: str) -> bool:
    try:
        models = fetch_ollama_models()
    except Exception as exc:
        return add_check(checks, "ollama", False, f"Ollama tags request failed: {exc.__class__.__name__}")
    if model not in models:
        return add_check(checks, "ollama", False, "missing_ollama_model")
    return add_check(checks, "ollama", True, "ok")


def check_compose_config(checks: list[dict[str, object]], env_file: Path, compose_file: Path, project_name: str) -> bool:
    return check_command(checks, "compose_config", [
        "docker", "compose", "--env-file", str(env_file),
        "-f", str(compose_file), "-p", project_name, "config", "--quiet",
    ])


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run X-Agent R2 local preflight checks.")
    parser.add_argument("--env-file", type=Path, default=Path("deploy/compose/r2.env.local"))
    parser.add_argument("--compose-file", type=Path, default=Path("deploy/compose/docker-compose.yml"))
    parser.add_argument("--project-name", default="xagent-r2")
    parser.add_argument("--expected-branch", default="feature/webapi-r2-staging-readiness")
    parser.add_argument("--output", type=Path, default=Path("output/r2-runtime/preflight.json"))
    parser.add_argument("--init-env", type=Path)
    parser.add_argument("--validate-env-only", action="store_true")
    parser.add_argument("--allow-running-project", action="store_true")
    return parser.parse_args(argv)


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env_file = resolve(args.env_file)
    compose_file = resolve(args.compose_file)
    output = resolve(args.output)
    checks: list[dict[str, object]] = []
    branch = ""
    commit = ""

    try:
        if args.init_env is not None:
            init_target = resolve(args.init_env)
            init_env(init_target.with_name("r2.env.example"), init_target)
            env_file = init_target

        values = load_env(env_file)
        errors = validate_env(values)
        add_check(checks, "env", not errors, "ok" if not errors else ",".join(item["code"] for item in errors))

        if not errors and args.init_env is None and not args.validate_env_only:
            git_ok, branch, commit = check_git(checks, args.expected_branch)
            if git_ok:
                check_command(checks, "docker", ["docker", "version"])
            if all(check["ok"] for check in checks):
                check_command(checks, "docker_compose", ["docker", "compose", "version"])
            if all(check["ok"] for check in checks):
                check_ports(checks, values, env_file, compose_file, args.project_name, args.allow_running_project)
            if all(check["ok"] for check in checks):
                check_ollama(checks, values.get("XAGENT_LLM__OLLAMA_MODEL", "").strip())
            if all(check["ok"] for check in checks):
                check_compose_config(checks, env_file, compose_file, args.project_name)
    except Exception as exc:
        add_check(checks, "exception", False, exc.__class__.__name__)

    report = make_report(checks, branch, commit)
    write_report(output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
