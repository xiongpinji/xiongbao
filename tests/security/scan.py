"""Fail-closed security scan for authentication, isolation, headers and rate limits."""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


REQUIRED_CHECKS = (
    "health",
    "nosniff",
    "frame_deny",
    "auth_required",
    "tenant_header_injection",
    "tenant_memory_isolation",
    "sql_injection",
    "rate_limit",
)


def request_count_for_rate_limit(configured_limit: int) -> int:
    if configured_limit < 1:
        raise ValueError("configured_limit must be positive")
    return configured_limit + 2


def required_results(results: Mapping[str, CheckResult]) -> list[CheckResult]:
    return [
        results.get(name, CheckResult(name, False, "missing"))
        for name in REQUIRED_CHECKS
    ]


def exit_code(results: Sequence[CheckResult]) -> int:
    counts = Counter(item.name for item in results)
    if set(counts) != set(REQUIRED_CHECKS):
        return 1
    if any(counts[name] != 1 for name in REQUIRED_CHECKS):
        return 1
    return 0 if all(item.passed for item in results) else 1


def _record(
    results: dict[str, CheckResult], name: str, passed: bool, detail: str
) -> None:
    results[name] = CheckResult(name, passed, detail)


async def scan(
    host: str,
    *,
    expected_mode: str,
    configured_limit: int,
) -> list[CheckResult]:
    results: dict[str, CheckResult] = {}
    token_a = ""
    print(f"\n安全扫描：{host}\n")

    try:
        async with httpx.AsyncClient(base_url=host, timeout=15) as client:
            response = await client.get("/health")
            _record(results, "health", response.status_code == 200, str(response.status_code))
            _record(
                results,
                "nosniff",
                response.headers.get("X-Content-Type-Options") == "nosniff",
                response.headers.get("X-Content-Type-Options", "missing"),
            )
            _record(
                results,
                "frame_deny",
                response.headers.get("X-Frame-Options") == "DENY",
                response.headers.get("X-Frame-Options", "missing"),
            )

            response = await client.get("/api/v1/agents/roles")
            auth_passed = (
                response.status_code == 401
                if expected_mode in {"full", "enterprise"}
                else response.status_code in {200, 401}
            )
            _record(results, "auth_required", auth_passed, str(response.status_code))

            suffix = secrets.token_hex(6)
            register_a = await client.post(
                "/api/v1/auth/register",
                json={"username": f"sec_a_{suffix}", "password": "pass123456"},
            )
            register_b = await client.post(
                "/api/v1/auth/register",
                json={"username": f"sec_b_{suffix}", "password": "pass123456"},
            )
            registrations_ok = (
                register_a.status_code == 200 and register_b.status_code == 200
            )
            if registrations_ok:
                token_a = register_a.json()["access_token"]
                token_b = register_b.json()["access_token"]
                tenant_b = register_b.json()["tenant_id"]
                memory_id = f"security-scan-{suffix}"
                write_response = await client.post(
                    "/api/v1/memory",
                    json={"items": [{"id": memory_id, "text": "tenant-a-marker"}]},
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                header_response = await client.get(
                    "/api/v1/agents/roles",
                    headers={
                        "Authorization": f"Bearer {token_a}",
                        "X-Tenant-Id": tenant_b,
                    },
                )
                _record(
                    results,
                    "tenant_header_injection",
                    header_response.status_code == 403,
                    str(header_response.status_code),
                )
                if write_response.status_code == 200:
                    search_response = await client.post(
                        "/api/v1/memory/search",
                        json={"query": "tenant-a-marker", "top_k": 10},
                        headers={"Authorization": f"Bearer {token_b}"},
                    )
                    if search_response.status_code == 200:
                        ids = {
                            hit.get("id")
                            for hit in search_response.json().get("hits", [])
                        }
                        _record(
                            results,
                            "tenant_memory_isolation",
                            memory_id not in ids,
                            f"status={search_response.status_code}",
                        )
                    else:
                        _record(
                            results,
                            "tenant_memory_isolation",
                            False,
                            f"search_status={search_response.status_code}",
                        )
                else:
                    _record(
                        results,
                        "tenant_memory_isolation",
                        False,
                        f"write_status={write_response.status_code}",
                    )
            else:
                detail = f"register_status={register_a.status_code},{register_b.status_code}"
                _record(results, "tenant_header_injection", False, detail)
                _record(results, "tenant_memory_isolation", False, detail)

            if token_a:
                response = await client.post(
                    "/api/v1/memory/search",
                    json={"query": "'; DROP TABLE users; --", "top_k": 3},
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                _record(
                    results,
                    "sql_injection",
                    response.status_code == 200,
                    str(response.status_code),
                )
            else:
                _record(results, "sql_injection", False, "no_test_identity")

            rate_codes: list[int] = []
            for _ in range(request_count_for_rate_limit(configured_limit)):
                response = await client.get("/api/v1/agents/roles")
                rate_codes.append(response.status_code)
                if response.status_code == 429:
                    break
            _record(
                results,
                "rate_limit",
                429 in rate_codes,
                f"requests={len(rate_codes)} status_429={rate_codes.count(429)}",
            )
    except httpx.RequestError as exc:
        print(f"  request_failed: {type(exc).__name__}")

    return required_results(results)


def _print_results(results: Sequence[CheckResult]) -> None:
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"  [{mark}] {result.name}: {result.detail}")
    print("\nPASS" if exit_code(results) == 0 else "\nFAIL")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument(
        "--expected-mode",
        choices=("lite", "full", "enterprise"),
        required=True,
    )
    parser.add_argument("--rate-limit-requests", type=int, required=True)
    args = parser.parse_args(argv)

    try:
        request_count_for_rate_limit(args.rate_limit_requests)
    except ValueError as exc:
        parser.error(str(exc))
    results = asyncio.run(
        scan(
            args.host,
            expected_mode=args.expected_mode,
            configured_limit=args.rate_limit_requests,
        )
    )
    _print_results(results)
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
