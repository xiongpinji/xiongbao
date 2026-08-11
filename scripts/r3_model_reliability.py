from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Sequence


class SampleKind(StrEnum):
    CHAT = "chat"
    SCHEDULER = "scheduler"
    FILE_WRITE = "file_write"


class BatchStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


class FailureCode(StrEnum):
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    MODEL_EMPTY_RESPONSE = "model_empty_response"
    WRONG_FINAL = "wrong_final"
    FALSE_SUCCESS = "false_success"
    MISSING_PERSISTENCE = "missing_persistence"
    MISSING_CHECKPOINT = "missing_checkpoint"
    SCHEDULER_TERMINAL_ERROR = "scheduler_terminal_error"
    MISSING_ARTIFACT = "missing_artifact"
    PATCH_MISMATCH = "patch_mismatch"
    CLEANUP_FAILED = "cleanup_failed"
    MOCK_DETECTED = "mock_detected"
    FORBIDDEN_ROUTE = "forbidden_route"
    TENANT_ISOLATION_BREACH = "tenant_isolation_breach"
    HARNESS_ERROR = "harness_error"


@dataclass(frozen=True, slots=True)
class SampleSpec:
    batch_id: str
    sample_id: str
    kind: SampleKind
    index: int
    marker: str
    filename: str = ""


@dataclass(frozen=True, slots=True)
class SampleResult:
    batch_id: str
    sample_id: str
    kind: SampleKind
    index: int
    marker: str
    started_at: str
    finished_at: str
    duration_seconds: float
    http_status: int
    terminal_status: str
    success: bool
    exact_match: bool
    false_success: bool
    fail_closed: bool | None
    model: str = "qwen3:4b"
    route: str = ""
    tool_mode: str = ""
    run_id: str = ""
    task_id: str = ""
    conversation_id: str = ""
    checkpoint_id: str = ""
    job_id: str = ""
    development_task_id: str = ""
    error_code: str = ""
    error: str = ""
    finish_reason: str = "unknown"
    tool_call_count: int = 0
    artifact_count: int = 0
    patch_sha256: str = ""
    cleanup_ok: bool = True
    mock_detected: bool = False
    forbidden_route_detected: bool = False


@dataclass(frozen=True, slots=True)
class LogsAudit:
    mock_hits: int = 0
    forbidden_route_hits: int = 0
    traceback_hits: int = 0
    qwen_route_hits: int = 0


@dataclass(frozen=True, slots=True)
class BatchSummary:
    batch_id: str
    status: BatchStatus
    planned_samples: int
    completed_samples: int
    by_kind: dict[str, dict[str, Any]]
    false_success_count: int
    failed_sample_count: int
    fail_closed: bool | str
    isolation_ok: bool
    logs_audit: LogsAudit
    hard_failures: tuple[str, ...] = field(default_factory=tuple)
    aborted_error: str = ""


SAMPLE_COUNTS = {
    SampleKind.CHAT: 30,
    SampleKind.SCHEDULER: 10,
    SampleKind.FILE_WRITE: 10,
}
SUCCESS_THRESHOLDS = {
    SampleKind.CHAT: 29,
    SampleKind.SCHEDULER: 9,
    SampleKind.FILE_WRITE: 9,
}
P95_THRESHOLDS = {
    SampleKind.CHAT: 120.0,
    SampleKind.SCHEDULER: 180.0,
    SampleKind.FILE_WRITE: 240.0,
}


def build_sample_plan(batch_id: str) -> tuple[SampleSpec, ...]:
    safe_file_batch = batch_id.replace("-", "_")
    rows: list[SampleSpec] = []
    for kind, count, label in (
        (SampleKind.CHAT, 30, "CHAT"),
        (SampleKind.SCHEDULER, 10, "SCHEDULER"),
        (SampleKind.FILE_WRITE, 10, "FILE-WRITE"),
    ):
        for index in range(1, count + 1):
            sample_id = f"{kind.value.replace('_', '-')}-{index:03d}"
            filename = (
                f"R3_RELIABILITY_{safe_file_batch}_{index:03d}.md"
                if kind is SampleKind.FILE_WRITE
                else ""
            )
            rows.append(
                SampleSpec(
                    batch_id=batch_id,
                    sample_id=sample_id,
                    kind=kind,
                    index=index,
                    marker=f"R3-{label}-{batch_id}-{index:03d}",
                    filename=filename,
                )
            )
    return tuple(rows)


def nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    rank = math.ceil(percentile * len(ordered))
    return ordered[rank - 1]


def build_summary(
    batch_id: str,
    results: Sequence[SampleResult],
    *,
    logs_audit: LogsAudit,
    isolation_ok: bool,
    aborted_error: str = "",
) -> BatchSummary:
    by_kind: dict[str, dict[str, Any]] = {}
    for kind in SampleKind:
        items = [item for item in results if item.kind is kind]
        by_kind[kind.value] = {
            "planned": SAMPLE_COUNTS[kind],
            "completed": len(items),
            "succeeded": sum(item.success for item in items),
            "p95_seconds": (
                nearest_rank_percentile([item.duration_seconds for item in items], 0.95)
                if items
                else None
            ),
            "success_threshold": SUCCESS_THRESHOLDS[kind],
            "p95_threshold_seconds": P95_THRESHOLDS[kind],
        }

    failures = [item for item in results if not item.success]
    fail_closed: bool | str = (
        "not_applicable"
        if not failures
        else all(item.fail_closed is True for item in failures)
    )
    hard_failures: list[str] = []
    if any(item.false_success for item in results):
        hard_failures.append("false_success")
    if fail_closed is False:
        hard_failures.append("fail_closed")
    if logs_audit.mock_hits or any(item.mock_detected for item in results):
        hard_failures.append("mock_detected")
    if logs_audit.forbidden_route_hits or any(
        item.forbidden_route_detected for item in results
    ):
        hard_failures.append("forbidden_route")
    if not isolation_ok:
        hard_failures.append("tenant_isolation_breach")

    complete = len(results) == 50 and all(
        by_kind[kind.value]["completed"] == SAMPLE_COUNTS[kind] for kind in SampleKind
    )
    slo_ok = complete and all(
        by_kind[kind.value]["succeeded"] >= SUCCESS_THRESHOLDS[kind]
        and by_kind[kind.value]["p95_seconds"] <= P95_THRESHOLDS[kind]
        for kind in SampleKind
    )
    status = (
        BatchStatus.ABORTED
        if aborted_error or not complete
        else BatchStatus.PASSED
        if slo_ok and not hard_failures
        else BatchStatus.FAILED
    )
    return BatchSummary(
        batch_id=batch_id,
        status=status,
        planned_samples=50,
        completed_samples=len(results),
        by_kind=by_kind,
        false_success_count=sum(item.false_success for item in results),
        failed_sample_count=len(failures),
        fail_closed=fail_closed,
        isolation_ok=isolation_ok,
        logs_audit=logs_audit,
        hard_failures=tuple(hard_failures),
        aborted_error=aborted_error,
    )
