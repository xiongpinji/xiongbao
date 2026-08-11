from __future__ import annotations

import math
import json
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Sequence


_SECRET_PATTERNS = (
    re.compile(r"(?i)Bearer\s+[^\s]+"),
    re.compile(r"(?i)(password|token|authorization)\s*[:=]\s*[^\s,;]+"),
)


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

    def to_public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["error"] = sanitize_error(self.error)
        return payload


@dataclass(frozen=True, slots=True)
class LogsAudit:
    mock_hits: int = 0
    forbidden_route_hits: int = 0
    traceback_hits: int = 0
    qwen_route_hits: int = 0

    def to_public_dict(self) -> dict[str, int]:
        return asdict(self)


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

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "planned_samples": self.planned_samples,
            "completed_samples": self.completed_samples,
            "by_kind": self.by_kind,
            "false_success_count": self.false_success_count,
            "failed_sample_count": self.failed_sample_count,
            "fail_closed": self.fail_closed,
            "isolation_ok": self.isolation_ok,
            "logs_audit": self.logs_audit.to_public_dict(),
            "hard_failures": list(self.hard_failures),
            "aborted_error": sanitize_error(self.aborted_error),
        }


class BatchRecorder:
    def __init__(self, root: Path, batch_id: str) -> None:
        self.directory = root / batch_id
        self.samples_path = self.directory / "samples.jsonl"
        self._started = False
        self._finalized = False

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=False)
        self.samples_path.touch(exist_ok=False)
        self._started = True

    def append(self, result: SampleResult) -> None:
        if not self._started or self._finalized:
            raise RuntimeError("batch recorder is not writable")
        with self.samples_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(result.to_public_dict(), ensure_ascii=False) + "\n")

    def finalize(self, summary: BatchSummary, logs_audit: LogsAudit) -> None:
        if not self._started or self._finalized:
            raise RuntimeError("batch recorder cannot be finalized")
        self._write_json("summary.json", summary.to_public_dict())
        self._write_json("logs-audit.json", logs_audit.to_public_dict())
        self._finalized = True

    def _write_json(self, filename: str, payload: dict[str, Any]) -> None:
        path = self.directory / filename
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


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


def sanitize_error(value: str) -> str:
    text = str(value or "")[:1000]
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


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


def render_markdown_report(summary: BatchSummary) -> str:
    rows = []
    for kind in SampleKind:
        metrics = summary.by_kind[kind.value]
        p95 = metrics["p95_seconds"]
        p95_text = "unknown" if p95 is None else f"{p95:.3f}"
        rows.append(
            f"| {kind.value} | {metrics['completed']}/{metrics['planned']} | "
            f"{metrics['succeeded']} | {p95_text} |"
        )
    hard_failures = ", ".join(summary.hard_failures) or "无"
    aborted_error = sanitize_error(summary.aborted_error) or "无"
    return "\n".join(
        [
            "# X-Agent Web/API R3-A 真实模型可靠性基线",
            "",
            f"- 批次：`{summary.batch_id}`",
            f"- 状态：`{summary.status.value}`",
            f"- 完成样本：{summary.completed_samples}/{summary.planned_samples}",
            f"- 假成功：{summary.false_success_count}",
            f"- Fail-closed：{summary.fail_closed}",
            f"- 租户隔离：{'通过' if summary.isolation_ok else '失败'}",
            f"- MockLLM 命中：{summary.logs_audit.mock_hits}",
            f"- Forbidden route 命中：{summary.logs_audit.forbidden_route_hits}",
            f"- 硬失败：{hard_failures}",
            f"- 中断原因：{aborted_error}",
            "",
            "| 类型 | 完成/计划 | 精确成功 | P95 秒 |",
            "| --- | ---: | ---: | ---: |",
            *rows,
            "",
        ]
    )
