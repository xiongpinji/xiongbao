from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Sequence

import httpx


_SECRET_PATTERNS = (
    re.compile(r"(?i)Bearer\s+[^\s]+"),
    re.compile(r"(?i)(password|token|authorization)\s*[:=]\s*[^\s,;]+"),
)
FORBIDDEN_ROUTE_PATTERNS = (
    "/creative",
    "/canvas",
    "/editor",
    "/media/generate",
    "/media/tasks",
    "/produce",
)
ShellRunner = Callable[..., subprocess.CompletedProcess[str]]


class HarnessError(RuntimeError):
    """测试工具合同、解析或本地执行错误；它会中止批次。"""


class ProductApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client or httpx.Client()
        self.business_submissions: set[tuple[str, str]] = set()
        self.forbidden_route_detected = False

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if any(pattern in path for pattern in FORBIDDEN_ROUTE_PATTERNS):
            self.forbidden_route_detected = True
        supplied_headers = kwargs.pop("headers", {})
        headers = {**self._headers(), **supplied_headers}
        return self.client.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            **kwargs,
        )

    def claim_submission(self, sample_id: str, path: str) -> None:
        key = (sample_id, path)
        if key in self.business_submissions:
            raise RuntimeError(f"duplicate business submission: {sample_id} {path}")
        self.business_submissions.add(key)

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}


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
class ComposeTarget:
    compose_file: Path
    env_file: Path
    project_name: str

    def command(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--env-file",
            str(self.env_file),
            "-f",
            str(self.compose_file),
            "-p",
            self.project_name,
            *args,
        ]


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


def parse_sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name = "message"
    data_lines: list[str] = []

    def emit() -> None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            return
        raw = "\n".join(data_lines)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HarnessError(f"invalid SSE JSON for {event_name}") from exc
        if not isinstance(payload, dict):
            raise HarnessError(f"SSE payload for {event_name} must be an object")
        events.append((event_name, payload))
        event_name = "message"
        data_lines = []

    for line in response.iter_lines():
        if not line:
            emit()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())
    emit()
    return events


def _chat_failure_result(
    spec: SampleSpec,
    *,
    started_at: str,
    started_monotonic: float,
    model: str,
    http_status: int,
    error_code: FailureCode,
    error: str,
    terminal_status: str = "failed",
    fail_closed: bool = False,
    run_id: str = "",
    conversation_id: str = "",
    route: str = "",
    tool_mode: str = "",
    exact_match: bool = False,
    false_success: bool = False,
    tool_call_count: int = 0,
    checkpoint_id: str = "",
    finish_reason: str = "unknown",
    forbidden_route_detected: bool = False,
    mock_detected: bool = False,
) -> SampleResult:
    return SampleResult(
        batch_id=spec.batch_id,
        sample_id=spec.sample_id,
        kind=spec.kind,
        index=spec.index,
        marker=spec.marker,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        duration_seconds=max(0.0, time.monotonic() - started_monotonic),
        http_status=http_status,
        terminal_status=terminal_status,
        success=False,
        exact_match=exact_match,
        false_success=false_success,
        fail_closed=fail_closed,
        model=model,
        route=route,
        tool_mode=tool_mode,
        run_id=run_id,
        task_id=run_id,
        conversation_id=conversation_id,
        checkpoint_id=checkpoint_id,
        error_code=error_code.value,
        error=error,
        finish_reason=finish_reason,
        tool_call_count=tool_call_count,
        mock_detected=mock_detected,
        forbidden_route_detected=forbidden_route_detected,
    )


def run_chat_sample(
    api: ProductApiClient,
    spec: SampleSpec,
    *,
    model: str,
) -> SampleResult:
    if spec.kind is not SampleKind.CHAT:
        raise ValueError("chat executor requires a chat sample")
    path = "/stream/agents/run"
    api.claim_submission(spec.sample_id, path)
    started_at = datetime.now(UTC).isoformat()
    started_monotonic = time.monotonic()
    try:
        response = api.request(
            "POST",
            path,
            json={
                "goal": f"请只回复：{spec.marker}",
                "tool_mode": "none",
                "capabilities": [],
            },
            timeout=600.0,
        )
    except httpx.TimeoutException as exc:
        return _chat_failure_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=0,
            error_code=FailureCode.TIMEOUT,
            error=str(exc) or "chat request timed out",
            forbidden_route_detected=api.forbidden_route_detected,
        )
    except httpx.HTTPError as exc:
        return _chat_failure_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=0,
            error_code=FailureCode.HTTP_ERROR,
            error=str(exc),
            forbidden_route_detected=api.forbidden_route_detected,
        )
    if not response.is_success:
        return _chat_failure_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=response.status_code,
            error_code=FailureCode.HTTP_ERROR,
            error=f"chat HTTP {response.status_code}",
            forbidden_route_detected=api.forbidden_route_detected,
        )

    events = parse_sse(response)
    started_payload = next(
        (payload for event, payload in events if event == "started"), {}
    )
    final_payloads = [payload for event, payload in events if event == "final"]
    done_payloads = [payload for event, payload in events if event == "done"]
    error_payloads = [payload for event, payload in events if event == "error"]
    tool_call_count = sum(
        1
        for event, payload in events
        if event in {"tool_call", "tool_result"}
        or payload.get("kind") in {"tool_call", "tool_result"}
    )
    run_id = str(
        started_payload.get("run_id")
        or (done_payloads[-1].get("run_id") if done_payloads else "")
        or (error_payloads[-1].get("run_id") if error_payloads else "")
        or ""
    )
    conversation_id = str(started_payload.get("conversation_id") or "")
    started_route = str(started_payload.get("route") or "")
    sse_final = str(final_payloads[-1].get("content") or "") if final_payloads else ""
    sse_error = (
        str(error_payloads[-1].get("error") or error_payloads[-1].get("content") or "")
        if error_payloads
        else ""
    )

    task: dict[str, Any] = {}
    runtime_payload: dict[str, Any] = {}
    if run_id:
        runtime_response = api.request("GET", f"/runs/{run_id}", timeout=30.0)
        if runtime_response.is_success:
            runtime_payload = runtime_response.json()
            value = runtime_payload.get("task")
            if isinstance(value, dict):
                task = value
    task_input = task.get("input") if isinstance(task.get("input"), dict) else {}
    task_result = task.get("result") if isinstance(task.get("result"), dict) else {}
    terminal_status = str(task.get("status") or "unknown")
    persisted_final = str(task_result.get("final_answer") or "")
    persisted_error = str(task.get("error") or task_result.get("error") or "")
    route = str(task_input.get("route") or started_route)
    tool_mode = str(task_input.get("tool_mode") or "")
    finish_reason = str(
        task_result.get("finish_reason")
        or (done_payloads[-1].get("finish_reason") if done_payloads else "")
        or "unknown"
    )

    checkpoint_id = ""
    if run_id:
        checkpoint_response = api.request(
            "GET",
            "/checkpoints",
            params={"run_id": run_id},
            timeout=30.0,
        )
        if checkpoint_response.is_success:
            checkpoint_payload = checkpoint_response.json()
            checkpoints = checkpoint_payload.get("checkpoints") or []
            if checkpoints and isinstance(checkpoints[0], dict):
                checkpoint_id = str(checkpoints[0].get("checkpoint_id") or "")

    assistant_final = ""
    conversation_loaded = False
    if conversation_id:
        conversation_response = api.request(
            "GET",
            f"/stream/conversations/{conversation_id}/messages",
            timeout=30.0,
        )
        if conversation_response.is_success:
            conversation_loaded = True
            messages = conversation_response.json().get("messages") or []
            assistant_messages = [
                str(message.get("content") or "")
                for message in messages
                if isinstance(message, dict) and message.get("role") == "assistant"
            ]
            if assistant_messages:
                assistant_final = assistant_messages[-1]

    mock_detected = "MockLLM" in json.dumps(
        {"events": events, "runtime": runtime_payload},
        ensure_ascii=False,
    )
    exact_match = (
        len(final_payloads) == 1
        and sse_final == spec.marker
        and persisted_final == spec.marker
        and assistant_final == spec.marker
    )
    common = {
        "started_at": started_at,
        "started_monotonic": started_monotonic,
        "model": model,
        "http_status": response.status_code,
        "terminal_status": terminal_status,
        "run_id": run_id,
        "conversation_id": conversation_id,
        "route": route,
        "tool_mode": tool_mode,
        "exact_match": exact_match,
        "tool_call_count": tool_call_count,
        "checkpoint_id": checkpoint_id,
        "finish_reason": finish_reason,
        "forbidden_route_detected": api.forbidden_route_detected,
        "mock_detected": mock_detected,
    }

    if terminal_status != "succeeded":
        error = (
            persisted_error or sse_error or f"chat terminal status {terminal_status}"
        )
        fail_closed = bool(error) and not done_payloads and not final_payloads
        error_code = (
            FailureCode.WRONG_FINAL
            if done_payloads or final_payloads
            else FailureCode.MODEL_EMPTY_RESPONSE
            if "model_empty_response_after_retry" in error
            else FailureCode.HTTP_ERROR
        )
        return _chat_failure_result(
            spec,
            error_code=error_code,
            error=error,
            fail_closed=fail_closed,
            **common,
        )

    if not task or not conversation_loaded:
        return _chat_failure_result(
            spec,
            error_code=FailureCode.MISSING_PERSISTENCE,
            error="chat persistence is incomplete",
            **common,
        )
    contract_mismatch = (
        not exact_match
        or len(done_payloads) != 1
        or bool(error_payloads)
        or tool_call_count != 0
        or route != "chat_no_tools"
        or tool_mode != "none"
    )
    if contract_mismatch:
        return _chat_failure_result(
            spec,
            error_code=FailureCode.FALSE_SUCCESS,
            error="chat contract mismatch",
            false_success=True,
            **common,
        )
    if not checkpoint_id:
        return _chat_failure_result(
            spec,
            error_code=FailureCode.MISSING_CHECKPOINT,
            error="chat checkpoint is missing",
            **common,
        )
    return SampleResult(
        batch_id=spec.batch_id,
        sample_id=spec.sample_id,
        kind=spec.kind,
        index=spec.index,
        marker=spec.marker,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        duration_seconds=max(0.0, time.monotonic() - started_monotonic),
        http_status=response.status_code,
        terminal_status=terminal_status,
        success=True,
        exact_match=True,
        false_success=False,
        fail_closed=None,
        model=model,
        route=route,
        tool_mode=tool_mode,
        run_id=run_id,
        task_id=run_id,
        conversation_id=conversation_id,
        checkpoint_id=checkpoint_id,
        finish_reason=finish_reason,
        tool_call_count=0,
        mock_detected=mock_detected,
        forbidden_route_detected=api.forbidden_route_detected,
    )


def _scheduler_result(
    spec: SampleSpec,
    *,
    started_at: str,
    started_monotonic: float,
    model: str,
    http_status: int,
    terminal_status: str,
    success: bool,
    exact_match: bool,
    false_success: bool,
    fail_closed: bool | None,
    run_id: str = "",
    task_id: str = "",
    job_id: str = "",
    error_code: FailureCode | None = None,
    error: str = "",
    cleanup_ok: bool = True,
    forbidden_route_detected: bool = False,
) -> SampleResult:
    return SampleResult(
        batch_id=spec.batch_id,
        sample_id=spec.sample_id,
        kind=spec.kind,
        index=spec.index,
        marker=spec.marker,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        duration_seconds=max(0.0, time.monotonic() - started_monotonic),
        http_status=http_status,
        terminal_status=terminal_status,
        success=success,
        exact_match=exact_match,
        false_success=false_success,
        fail_closed=fail_closed,
        model=model,
        route="scheduler",
        tool_mode="auto",
        run_id=run_id,
        task_id=task_id,
        job_id=job_id,
        error_code=error_code.value if error_code else "",
        error=error,
        artifact_count=1 if task_id else 0,
        cleanup_ok=cleanup_ok,
        forbidden_route_detected=forbidden_route_detected,
    )


def _pause_scheduler_job(api: ProductApiClient, job_id: str) -> bool:
    try:
        response = api.request(
            "PATCH",
            f"/scheduler/jobs/{job_id}/toggle",
            json={"confirm_job_id": job_id, "enabled": False},
            timeout=30.0,
        )
        if not response.is_success or response.json().get("enabled") is not False:
            return False
        jobs_response = api.request("GET", "/scheduler/jobs", timeout=30.0)
        if not jobs_response.is_success:
            return False
        jobs = jobs_response.json().get("jobs") or []
        return any(
            isinstance(job, dict)
            and job.get("job_id") == job_id
            and job.get("enabled") is False
            for job in jobs
        )
    except (httpx.HTTPError, ValueError, TypeError):
        return False


def run_scheduler_sample(
    api: ProductApiClient,
    spec: SampleSpec,
    *,
    model: str,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> SampleResult:
    if spec.kind is not SampleKind.SCHEDULER:
        raise ValueError("scheduler executor requires a scheduler sample")
    create_path = "/scheduler/jobs"
    api.claim_submission(spec.sample_id, create_path)
    started_at = datetime.now(UTC).isoformat()
    started_monotonic = time.monotonic()
    try:
        create_response = api.request(
            "POST",
            create_path,
            json={
                "name": f"R3 reliability {spec.batch_id} {spec.index:03d}",
                "goal": f"请只回复：{spec.marker}",
                "role": None,
                "interval_seconds": 86_400,
                "max_retries": 0,
                "retry_backoff_seconds": 60,
            },
            timeout=30.0,
        )
    except httpx.TimeoutException as exc:
        return _scheduler_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=0,
            terminal_status="timeout",
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.TIMEOUT,
            error=str(exc) or "scheduler create timed out",
            forbidden_route_detected=api.forbidden_route_detected,
        )
    except httpx.HTTPError as exc:
        return _scheduler_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=0,
            terminal_status="failed",
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.HTTP_ERROR,
            error=str(exc),
            forbidden_route_detected=api.forbidden_route_detected,
        )
    if not create_response.is_success:
        return _scheduler_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=create_response.status_code,
            terminal_status="failed",
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.HTTP_ERROR,
            error=f"scheduler create HTTP {create_response.status_code}",
            forbidden_route_detected=api.forbidden_route_detected,
        )
    job_id = str(create_response.json().get("job_id") or "")
    if not job_id:
        return _scheduler_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=create_response.status_code,
            terminal_status="failed",
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.MISSING_PERSISTENCE,
            error="scheduler job id is missing",
            forbidden_route_detected=api.forbidden_route_detected,
        )

    scheduled_run_id = ""
    agent_run_id = ""
    terminal_status = "unknown"
    result_text = ""
    terminal_error = ""
    http_status = create_response.status_code
    sample_error_code: FailureCode | None = None
    cleanup_ok = False
    try:
        run_path = f"/scheduler/jobs/{job_id}/run"
        api.claim_submission(spec.sample_id, run_path)
        run_response = api.request(
            "POST",
            run_path,
            json={"confirm_job_id": job_id},
            timeout=30.0,
        )
        http_status = run_response.status_code
        if not run_response.is_success:
            sample_error_code = FailureCode.HTTP_ERROR
            terminal_error = f"scheduler run HTTP {run_response.status_code}"
        else:
            scheduled_run_id = str(run_response.json().get("run_id") or "")
            deadline = monotonic() + 600.0
            while True:
                runs_response = api.request(
                    "GET",
                    f"/scheduler/jobs/{job_id}/runs",
                    timeout=30.0,
                )
                http_status = runs_response.status_code
                if not runs_response.is_success:
                    sample_error_code = FailureCode.HTTP_ERROR
                    terminal_error = f"scheduler runs HTTP {runs_response.status_code}"
                    break
                runs = runs_response.json().get("runs") or []
                attempt_one = next(
                    (
                        run
                        for run in runs
                        if isinstance(run, dict)
                        and run.get("attempt") == 1
                        and (
                            not scheduled_run_id
                            or run.get("run_id") == scheduled_run_id
                        )
                    ),
                    None,
                )
                if attempt_one is not None:
                    terminal_status = str(attempt_one.get("status") or "unknown")
                    if terminal_status in {"succeeded", "failed", "interrupted"}:
                        scheduled_run_id = str(
                            attempt_one.get("run_id") or scheduled_run_id
                        )
                        agent_run_id = str(attempt_one.get("agent_run_id") or "")
                        result_text = str(attempt_one.get("result") or "")
                        terminal_error = str(attempt_one.get("error") or "")
                        break
                if monotonic() >= deadline:
                    terminal_status = "timeout"
                    sample_error_code = FailureCode.TIMEOUT
                    terminal_error = "scheduler attempt 1 timed out"
                    break
                sleep(2.0)
    except httpx.TimeoutException as exc:
        terminal_status = "timeout"
        sample_error_code = FailureCode.TIMEOUT
        terminal_error = str(exc) or "scheduler request timed out"
    except httpx.HTTPError as exc:
        terminal_status = "failed"
        sample_error_code = FailureCode.HTTP_ERROR
        terminal_error = str(exc)
    finally:
        cleanup_ok = _pause_scheduler_job(api, job_id)

    common = {
        "started_at": started_at,
        "started_monotonic": started_monotonic,
        "model": model,
        "http_status": http_status,
        "terminal_status": terminal_status,
        "run_id": agent_run_id,
        "task_id": scheduled_run_id,
        "job_id": job_id,
        "cleanup_ok": cleanup_ok,
        "forbidden_route_detected": api.forbidden_route_detected,
    }
    if not cleanup_ok:
        return _scheduler_result(
            spec,
            success=False,
            exact_match=result_text.strip() == spec.marker,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.CLEANUP_FAILED,
            error="scheduler job pause failed",
            **common,
        )
    if sample_error_code is not None:
        return _scheduler_result(
            spec,
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=sample_error_code,
            error=terminal_error,
            **common,
        )
    if terminal_status != "succeeded":
        return _scheduler_result(
            spec,
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=bool(terminal_error) and not result_text,
            error_code=FailureCode.SCHEDULER_TERMINAL_ERROR,
            error=terminal_error or f"scheduler terminal status {terminal_status}",
            **common,
        )
    exact_match = result_text.strip() == spec.marker
    if not exact_match or terminal_error or not agent_run_id:
        return _scheduler_result(
            spec,
            success=False,
            exact_match=exact_match,
            false_success=True,
            fail_closed=False,
            error_code=FailureCode.FALSE_SUCCESS,
            error="scheduler result contract mismatch",
            **common,
        )
    return _scheduler_result(
        spec,
        success=True,
        exact_match=True,
        false_success=False,
        fail_closed=None,
        **common,
    )


def _file_write_result(
    spec: SampleSpec,
    *,
    started_at: str,
    started_monotonic: float,
    model: str,
    http_status: int,
    terminal_status: str,
    success: bool,
    exact_match: bool,
    false_success: bool,
    fail_closed: bool | None,
    run_id: str = "",
    task_id: str = "",
    development_task_id: str = "",
    error_code: FailureCode | None = None,
    error: str = "",
    artifact_count: int = 0,
    patch_sha256: str = "",
    cleanup_ok: bool = True,
    forbidden_route_detected: bool = False,
) -> SampleResult:
    return SampleResult(
        batch_id=spec.batch_id,
        sample_id=spec.sample_id,
        kind=spec.kind,
        index=spec.index,
        marker=spec.marker,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        duration_seconds=max(0.0, time.monotonic() - started_monotonic),
        http_status=http_status,
        terminal_status=terminal_status,
        success=success,
        exact_match=exact_match,
        false_success=false_success,
        fail_closed=fail_closed,
        model=model,
        route="parallel_file_write",
        tool_mode="auto",
        run_id=run_id,
        task_id=task_id,
        development_task_id=development_task_id,
        error_code=error_code.value if error_code else "",
        error=error,
        artifact_count=artifact_count,
        patch_sha256=patch_sha256,
        cleanup_ok=cleanup_ok,
        forbidden_route_detected=forbidden_route_detected,
    )


def _compose_exec(
    compose: ComposeTarget,
    shell_runner: ShellRunner,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return shell_runner(
        compose.command("exec", "-T", "api", *args),
        capture_output=True,
        text=True,
        timeout=30.0,
        check=False,
    )


def _reject_file_write_task(
    api: ProductApiClient,
    compose: ComposeTarget,
    task_id: str,
    shell_runner: ShellRunner,
) -> bool:
    try:
        reject = api.request(
            "POST",
            f"/development-tasks/{task_id}/reject",
            json={"confirm_task_id": task_id},
            timeout=30.0,
        )
        if not reject.is_success:
            return False
        detail = api.request(
            "GET",
            f"/development-tasks/{task_id}",
            timeout=30.0,
        )
        if not detail.is_success or detail.json().get("status") != "rejected":
            return False
        worktree = _compose_exec(
            compose,
            shell_runner,
            "test",
            "!",
            "-d",
            f"/data/.xagent-worktrees/{task_id}",
        )
        branch = _compose_exec(
            compose,
            shell_runner,
            "git",
            "-C",
            "/data/workspace",
            "branch",
            "--list",
            f"agent/{task_id}",
        )
        return (
            worktree.returncode == 0
            and branch.returncode == 0
            and not branch.stdout.strip()
        )
    except (
        httpx.HTTPError,
        ValueError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
    ):
        return False


def run_file_write_sample(
    api: ProductApiClient,
    spec: SampleSpec,
    *,
    model: str,
    compose: ComposeTarget,
    shell_runner: ShellRunner = subprocess.run,
) -> SampleResult:
    if spec.kind is not SampleKind.FILE_WRITE:
        raise ValueError("file_write executor requires a file_write sample")
    path = "/agents/parallel-run"
    api.claim_submission(spec.sample_id, path)
    started_at = datetime.now(UTC).isoformat()
    started_monotonic = time.monotonic()
    try:
        response = api.request(
            "POST",
            path,
            json={
                "tasks": [
                    {
                        "goal": (
                            "必须调用 file_write 工具在当前工作区创建 "
                            f"{spec.filename}，文件内容必须精确为 {spec.marker}"
                            "（允许末尾换行），不得只用文字回答。"
                        ),
                        "capabilities": ["file_write"],
                    }
                ],
                "coordinator_goal": f"R3 可靠性样本 {spec.sample_id}",
                "use_worktrees": True,
            },
            timeout=300.0,
        )
    except httpx.TimeoutException as exc:
        return _file_write_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=0,
            terminal_status="timeout",
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.TIMEOUT,
            error=str(exc) or "file_write request timed out",
            forbidden_route_detected=api.forbidden_route_detected,
        )
    except httpx.HTTPError as exc:
        return _file_write_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=0,
            terminal_status="failed",
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.HTTP_ERROR,
            error=str(exc),
            forbidden_route_detected=api.forbidden_route_detected,
        )
    if not response.is_success:
        return _file_write_result(
            spec,
            started_at=started_at,
            started_monotonic=started_monotonic,
            model=model,
            http_status=response.status_code,
            terminal_status="failed",
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.HTTP_ERROR,
            error=f"file_write HTTP {response.status_code}",
            forbidden_route_detected=api.forbidden_route_detected,
        )

    payload = response.json()
    sub_results = payload.get("sub_results") or []
    sub = sub_results[0] if sub_results and isinstance(sub_results[0], dict) else {}
    parent_run_id = str(payload.get("run_id") or "")
    sub_run_id = str(sub.get("run_id") or "")
    terminal_status = str(sub.get("status") or "unknown")
    task_id = str(sub.get("development_task_id") or "")
    task_status = str(sub.get("development_task_status") or "")
    sub_error = str(sub.get("error") or "")
    safe_task_id = bool(re.fullmatch(r"[a-f0-9]{32}", task_id))
    detail: dict[str, Any] = {}
    patch = ""
    http_status = response.status_code
    artifact_count = 0
    patch_sha256 = ""
    inspection_error = ""
    cleanup_ok = True

    try:
        if safe_task_id:
            detail_response = api.request(
                "GET",
                f"/development-tasks/{task_id}",
                timeout=30.0,
            )
            http_status = detail_response.status_code
            if detail_response.is_success:
                detail = detail_response.json()
            else:
                inspection_error = (
                    f"development task HTTP {detail_response.status_code}"
                )
            readable_status = str(detail.get("status") or task_status)
            if readable_status == "awaiting_review":
                patch_response = api.request(
                    "GET",
                    f"/development-tasks/{task_id}/patch",
                    timeout=30.0,
                )
                http_status = patch_response.status_code
                if patch_response.is_success:
                    patch = str(patch_response.json().get("patch") or "")
                    patch_sha256 = hashlib.sha256(patch.encode()).hexdigest()
                elif not inspection_error:
                    inspection_error = f"patch HTTP {patch_response.status_code}"

            worktree = _compose_exec(
                compose,
                shell_runner,
                "test",
                "-d",
                f"/data/.xagent-worktrees/{task_id}",
            )
            worktree_ok = worktree.returncode == 0
            artifact_count += int(worktree_ok)

            result_commit = str(detail.get("result_commit") or "")
            commit_ok = False
            if worktree_ok and re.fullmatch(r"[a-f0-9]{40}", result_commit):
                commit = _compose_exec(
                    compose,
                    shell_runner,
                    "git",
                    "-C",
                    f"/data/.xagent-worktrees/{task_id}",
                    "cat-file",
                    "-e",
                    f"{result_commit}^{{commit}}",
                )
                commit_ok = commit.returncode == 0
            artifact_count += int(commit_ok)

            diff_stat = str(detail.get("diff_stat") or sub.get("diff_stat") or "")
            diff_text = str(sub.get("diff") or "")
            diff_ok = spec.filename in diff_stat and spec.marker in diff_text
            patch_ok = spec.filename in patch and spec.marker in patch
            artifact_count += int(diff_ok)
            artifact_count += int(patch_ok)
        else:
            worktree_ok = commit_ok = diff_ok = patch_ok = False
    except (
        httpx.HTTPError,
        ValueError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        worktree_ok = commit_ok = diff_ok = patch_ok = False
        inspection_error = str(exc)
    finally:
        if safe_task_id and (
            task_status == "awaiting_review"
            or str(detail.get("status") or "") == "awaiting_review"
        ):
            cleanup_ok = _reject_file_write_task(api, compose, task_id, shell_runner)

    common = {
        "started_at": started_at,
        "started_monotonic": started_monotonic,
        "model": model,
        "http_status": http_status,
        "terminal_status": terminal_status,
        "run_id": sub_run_id,
        "task_id": parent_run_id,
        "development_task_id": task_id,
        "artifact_count": artifact_count,
        "patch_sha256": patch_sha256,
        "cleanup_ok": cleanup_ok,
        "forbidden_route_detected": api.forbidden_route_detected,
    }
    if not cleanup_ok:
        return _file_write_result(
            spec,
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=False,
            error_code=FailureCode.CLEANUP_FAILED,
            error="development task reject cleanup failed",
            **common,
        )
    if terminal_status != "succeeded":
        failure_code = (
            FailureCode.MODEL_EMPTY_RESPONSE
            if "model_empty_response_after_retry" in sub_error
            else FailureCode.MISSING_ARTIFACT
        )
        return _file_write_result(
            spec,
            success=False,
            exact_match=False,
            false_success=False,
            fail_closed=bool(sub_error) and not patch,
            error_code=failure_code,
            error=sub_error or f"file_write terminal status {terminal_status}",
            **common,
        )
    contract_ok = (
        payload.get("status") == "succeeded"
        and sub.get("isolated") is True
        and task_status == "awaiting_review"
        and detail.get("status") == "awaiting_review"
        and artifact_count == 4
    )
    if not patch_ok:
        return _file_write_result(
            spec,
            success=False,
            exact_match=False,
            false_success=True,
            fail_closed=False,
            error_code=FailureCode.PATCH_MISMATCH,
            error="development task patch does not contain expected artifact",
            **common,
        )
    if not contract_ok:
        return _file_write_result(
            spec,
            success=False,
            exact_match=False,
            false_success=True,
            fail_closed=False,
            error_code=FailureCode.MISSING_ARTIFACT,
            error=inspection_error or "development task artifact contract mismatch",
            **common,
        )
    return _file_write_result(
        spec,
        success=True,
        exact_match=True,
        false_success=False,
        fail_closed=None,
        **common,
    )


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
