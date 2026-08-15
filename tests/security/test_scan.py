from __future__ import annotations

from tests.security.scan import (
    CheckResult,
    exit_code,
    request_count_for_rate_limit,
    required_results,
)


def test_failed_required_check_changes_exit_code() -> None:
    results = [
        CheckResult("health", True, "200"),
        CheckResult("auth_required", False, "200"),
    ]

    assert exit_code(results) == 1


def test_rate_limit_attempts_exceed_configured_threshold() -> None:
    assert request_count_for_rate_limit(configured_limit=3) == 5
    assert request_count_for_rate_limit(configured_limit=300) == 302


def test_missing_tenant_checks_fail_closed() -> None:
    results = required_results({
        "health": CheckResult("health", True, "200"),
    })

    assert {item.name for item in results if not item.passed} >= {
        "tenant_header_injection",
        "tenant_memory_isolation",
    }


def test_all_required_checks_must_appear_exactly_once() -> None:
    results = required_results({})
    duplicate = [*results, results[0]]

    assert exit_code(results) == 1
    assert exit_code(duplicate) == 1
