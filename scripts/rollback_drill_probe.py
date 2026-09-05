"""Seed and verify isolated rollback drill data through the public API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import tempfile
from pathlib import Path

import httpx

SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")


def _write_json_atomic(path: Path, value: object, *, private: bool = False) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if private:
            temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    token: str | None = None,
    expected: int = 200,
    **kwargs: object,
) -> httpx.Response:
    headers = dict(kwargs.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, path, headers=headers, **kwargs)
    if response.status_code != expected:
        raise RuntimeError(
            f"{method} {path} returned HTTP {response.status_code}, expected {expected}"
        )
    return response


def _register(
    client: httpx.Client, username: str, password: str, tenant_id: str
) -> str:
    body = _request(
        client,
        "POST",
        "/api/v1/auth/register",
        json={"username": username, "password": password, "tenant_id": tenant_id},
    ).json()
    if body.get("tenant_id") != tenant_id or not body.get("access_token"):
        raise RuntimeError("registration returned an invalid tenant identity")
    return str(body["access_token"])


def _login(client: httpx.Client, user: dict[str, object]) -> str:
    body = _request(
        client,
        "POST",
        "/api/v1/auth/login",
        json={
            "username": user["username"],
            "password": user["password"],
            "tenant_id": user["tenant_id"],
        },
    ).json()
    if body.get("tenant_id") != user["tenant_id"] or not body.get("access_token"):
        raise RuntimeError("login returned an invalid tenant identity")
    return str(body["access_token"])


def seed(
    *,
    api_url: str,
    source_sha: str,
    state_output: Path,
    evidence_output: Path,
    artifact_root: Path,
) -> None:
    nonce = secrets.token_hex(4)
    users: list[dict[str, object]] = []
    artifact_root.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=api_url, timeout=240) as client:
        for suffix in ("a", "b"):
            username = f"rollback-{source_sha[:8]}-{suffix}-{nonce}"
            tenant_id = f"rollback-{source_sha[:8]}-tenant-{suffix}-{nonce}"
            password = f"R-{secrets.token_urlsafe(32)}-aA1!"
            token = _register(client, username, password, tenant_id)
            memory_id = f"rollback-{source_sha[:8]}-memory-{suffix}-{nonce}"
            memory_text = f"rollback nonce {nonce} tenant {suffix}"
            written = _request(
                client,
                "POST",
                "/api/v1/memory",
                token=token,
                json={"items": [{"id": memory_id, "text": memory_text}]},
            ).json()
            if memory_id not in written.get("written", []):
                raise RuntimeError("memory write did not persist the expected id")

            job = _request(
                client,
                "POST",
                "/api/v1/scheduler/jobs",
                token=token,
                json={
                    "name": f"rollback {suffix}",
                    "goal": f"rollback-{source_sha[:8]}-{nonce}",
                    "interval_seconds": 3600,
                    "max_retries": 1,
                },
            ).json()
            job_id = str(job.get("job_id") or "")
            if not job_id:
                raise RuntimeError("scheduler did not return a job id")

            document = _request(
                client,
                "POST",
                "/api/v1/creative-studio/produce",
                token=token,
                json={
                    "brief": f"rollback local delivery {suffix} {nonce}",
                    "with_video": False,
                },
            ).json()
            if document.get("status") != "produced" or not document.get("storyboard_id"):
                raise RuntimeError("creative delivery did not reach produced")
            storyboard_id = str(document["storyboard_id"])
            bundle = _request(
                client,
                "GET",
                f"/api/v1/creative-studio/productions/{storyboard_id}/bundle",
                token=token,
            ).content
            bundle_hash = hashlib.sha256(bundle).hexdigest()
            bundle_path = artifact_root / f"candidate-short-drama-{suffix}.zip"
            bundle_path.write_bytes(bundle)

            audit = _request(client, "GET", "/api/v1/audit/verify", token=token).json()
            if audit.get("valid") is not True:
                raise RuntimeError("audit verification failed during seed")
            users.append(
                {
                    "username": username,
                    "password": password,
                    "tenant_id": tenant_id,
                    "token": token,
                    "memory_id": memory_id,
                    "memory_text": memory_text,
                    "scheduler_job_id": job_id,
                    "storyboard_id": storyboard_id,
                    "bundle_sha256": bundle_hash,
                }
            )

        hidden = _request(
            client,
            "POST",
            "/api/v1/memory/search",
            token=str(users[1]["token"]),
            json={"query": users[0]["memory_text"], "top_k": 10},
        ).json()
        if users[0]["memory_id"] in {item["id"] for item in hidden.get("hits", [])}:
            raise RuntimeError("cross-tenant memory was visible")
        _request(
            client,
            "GET",
            f"/api/v1/creative-studio/productions/{users[0]['storyboard_id']}",
            token=str(users[1]["token"]),
            expected=404,
        )
        audit_export = _request(
            client, "GET", "/api/v1/audit/export", token=str(users[0]["token"])
        ).content
        (artifact_root / "source-audit.json").write_bytes(audit_export)

    private_state = {
        "schema_version": "1.0",
        "source_sha": source_sha,
        "nonce": nonce,
        "users": users,
    }
    public_users = [
        {key: value for key, value in user.items() if key not in {"password", "token"}}
        for user in users
    ]
    _write_json_atomic(state_output, private_state, private=True)
    _write_json_atomic(
        evidence_output,
        {
            "schema_version": "1.0",
            "source_sha": source_sha,
            "tenant_isolation": "passed",
            "audit_chain": "passed",
            "users": public_users,
        },
    )


def verify(
    *, api_url: str, state_path: Path, phase: str, evidence_output: Path
) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    users = list(state["users"])
    results: list[dict[str, object]] = []
    with httpx.Client(base_url=api_url, timeout=240) as client:
        tokens = [_login(client, user) for user in users]
        for index, (user, token) in enumerate(zip(users, tokens, strict=True)):
            search = _request(
                client,
                "POST",
                "/api/v1/memory/search",
                token=token,
                json={"query": user["memory_text"], "top_k": 10},
            ).json()
            if user["memory_id"] not in {item["id"] for item in search.get("hits", [])}:
                raise RuntimeError(f"{phase} memory verification failed")
            jobs = _request(
                client, "GET", "/api/v1/scheduler/jobs", token=token
            ).json()
            if user["scheduler_job_id"] not in {
                item["job_id"] for item in jobs.get("jobs", [])
            }:
                raise RuntimeError(f"{phase} scheduler verification failed")
            document = _request(
                client,
                "GET",
                f"/api/v1/creative-studio/productions/{user['storyboard_id']}",
                token=token,
            ).json()
            if document.get("status") != "produced":
                raise RuntimeError(f"{phase} creative delivery verification failed")
            bundle = _request(
                client,
                "GET",
                f"/api/v1/creative-studio/productions/{user['storyboard_id']}/bundle",
                token=token,
            ).content
            bundle_hash = hashlib.sha256(bundle).hexdigest()
            if bundle_hash != user["bundle_sha256"]:
                raise RuntimeError(f"{phase} delivery bundle hash changed")
            other = users[1 - index]
            cross = _request(
                client,
                "POST",
                "/api/v1/memory/search",
                token=token,
                json={"query": other["memory_text"], "top_k": 10},
            ).json()
            if other["memory_id"] in {item["id"] for item in cross.get("hits", [])}:
                raise RuntimeError(f"{phase} cross-tenant memory was visible")
            _request(
                client,
                "GET",
                f"/api/v1/creative-studio/productions/{other['storyboard_id']}",
                token=token,
                expected=404,
            )
            audit = _request(client, "GET", "/api/v1/audit/verify", token=token).json()
            if audit.get("valid") is not True:
                raise RuntimeError(f"{phase} audit verification failed")
            results.append(
                {
                    "tenant_id": user["tenant_id"],
                    "memory_id": user["memory_id"],
                    "scheduler_job_id": user["scheduler_job_id"],
                    "storyboard_id": user["storyboard_id"],
                    "bundle_sha256": bundle_hash,
                }
            )
    _write_json_atomic(
        evidence_output,
        {
            "schema_version": "1.0",
            "source_sha": state["source_sha"],
            "phase": phase,
            "status": "passed",
            "tenant_isolation": "passed",
            "audit_chain": "passed",
            "users": results,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--api-url", required=True)
    seed_parser.add_argument("--source-sha", required=True)
    seed_parser.add_argument("--state-output", type=Path, required=True)
    seed_parser.add_argument("--evidence-output", type=Path, required=True)
    seed_parser.add_argument("--artifact-root", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--api-url", required=True)
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--phase", required=True)
    verify_parser.add_argument("--evidence-output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "seed":
        if SHA_PATTERN.fullmatch(args.source_sha) is None:
            raise ValueError("source SHA is invalid")
        if args.artifact_root.resolve() in args.state_output.resolve().parents:
            raise ValueError("private state must stay outside evidence artifacts")
        seed(
            api_url=args.api_url,
            source_sha=args.source_sha,
            state_output=args.state_output,
            evidence_output=args.evidence_output,
            artifact_root=args.artifact_root,
        )
    else:
        verify(
            api_url=args.api_url,
            state_path=args.state.resolve(strict=True),
            phase=args.phase,
            evidence_output=args.evidence_output,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
