from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

import httpx

from scripts.r3_model_reliability import (
    BatchRecorder,
    BatchRunOutcome,
    BatchStatus,
    ComposeTarget,
    ExecutionOutcome,
    FailureCode,
    IsolationProbeResult,
    LogsAudit,
    PreflightSnapshot,
    ProductApiClient,
    SampleKind,
    SampleResult,
    audit_logs,
    build_sample_plan,
    build_summary,
    cli,
    execute_sample_plan,
    generate_batch_id,
    nearest_rank_percentile,
    render_markdown_report,
    run_preflight,
    run_chat_sample,
    run_file_write_sample,
    run_reliability_batch,
    run_scheduler_sample,
    run_tenant_isolation_probe,
)


BATCH_ID = "20260811T010203Z-ab12cd"


def _sample_result(
    kind: SampleKind,
    index: int,
    *,
    success: bool = True,
    duration: float = 1.0,
    false_success: bool = False,
    fail_closed: bool | None = None,
) -> SampleResult:
    spec = next(
        item
        for item in build_sample_plan(BATCH_ID)
        if item.kind is kind and item.index == index
    )
    return SampleResult(
        batch_id=BATCH_ID,
        sample_id=spec.sample_id,
        kind=kind,
        index=index,
        marker=spec.marker,
        started_at="2026-08-11T01:02:03+00:00",
        finished_at="2026-08-11T01:02:04+00:00",
        duration_seconds=duration,
        http_status=200,
        terminal_status="succeeded" if success else "failed",
        success=success,
        exact_match=success,
        false_success=false_success,
        fail_closed=fail_closed,
    )


def _passing_results() -> list[SampleResult]:
    results = [_sample_result(SampleKind.CHAT, index) for index in range(1, 31)]
    results.extend(
        _sample_result(SampleKind.SCHEDULER, index) for index in range(1, 11)
    )
    results.extend(
        _sample_result(SampleKind.FILE_WRITE, index) for index in range(1, 11)
    )
    return results


class R3PlanAndSummaryTests(unittest.TestCase):
    def test_plan_is_fixed_order_and_has_unique_public_markers(self) -> None:
        plan = build_sample_plan(BATCH_ID)

        self.assertEqual(len(plan), 50)
        self.assertEqual([item.kind for item in plan[:30]], [SampleKind.CHAT] * 30)
        self.assertEqual(
            [item.kind for item in plan[30:40]], [SampleKind.SCHEDULER] * 10
        )
        self.assertEqual(
            [item.kind for item in plan[40:]], [SampleKind.FILE_WRITE] * 10
        )
        self.assertEqual(plan[0].sample_id, "chat-001")
        self.assertEqual(plan[30].sample_id, "scheduler-001")
        self.assertEqual(plan[40].sample_id, "file-write-001")
        self.assertEqual(len({item.marker for item in plan}), 50)
        self.assertEqual(plan[0].marker, f"R3-CHAT-{BATCH_ID}-001")
        self.assertEqual(
            plan[40].filename,
            "R3_RELIABILITY_20260811T010203Z_ab12cd_001.md",
        )

    def test_failure_code_taxonomy_is_fixed(self) -> None:
        self.assertEqual(
            {item.value for item in FailureCode},
            {
                "http_error",
                "timeout",
                "model_empty_response",
                "wrong_final",
                "false_success",
                "missing_persistence",
                "missing_checkpoint",
                "scheduler_terminal_error",
                "missing_artifact",
                "patch_mismatch",
                "cleanup_failed",
                "mock_detected",
                "forbidden_route",
                "tenant_isolation_breach",
                "harness_error",
            },
        )

    def test_nearest_rank_percentile_uses_ceil_rank(self) -> None:
        values = [float(value) for value in range(1, 31)]

        self.assertEqual(nearest_rank_percentile(values, 0.95), 29.0)
        self.assertEqual(nearest_rank_percentile([3.0, 1.0, 2.0], 0.95), 3.0)
        with self.assertRaises(ValueError):
            nearest_rank_percentile([], 0.95)
        with self.assertRaises(ValueError):
            nearest_rank_percentile([1.0], 0.0)

    def test_summary_passes_only_at_fixed_thresholds(self) -> None:
        summary = build_summary(
            BATCH_ID,
            _passing_results(),
            logs_audit=LogsAudit(qwen_route_hits=50),
            isolation_ok=True,
        )

        self.assertEqual(summary.status, BatchStatus.PASSED)
        self.assertEqual(summary.by_kind["chat"]["succeeded"], 30)
        self.assertEqual(summary.by_kind["chat"]["p95_seconds"], 1.0)
        self.assertEqual(summary.fail_closed, "not_applicable")
        self.assertEqual(summary.hard_failures, ())

    def test_summary_accepts_one_fail_closed_chat_failure(self) -> None:
        results = _passing_results()
        results[0] = _sample_result(
            SampleKind.CHAT,
            1,
            success=False,
            fail_closed=True,
        )

        summary = build_summary(
            BATCH_ID,
            results,
            logs_audit=LogsAudit(qwen_route_hits=50),
            isolation_ok=True,
        )

        self.assertEqual(summary.status, BatchStatus.PASSED)
        self.assertEqual(summary.by_kind["chat"]["succeeded"], 29)
        self.assertTrue(summary.fail_closed)

    def test_summary_fails_below_success_or_p95_threshold(self) -> None:
        results = _passing_results()
        results[0] = _sample_result(SampleKind.CHAT, 1, success=False, fail_closed=True)
        results[1] = _sample_result(SampleKind.CHAT, 2, success=False, fail_closed=True)
        results[28] = replace(results[28], duration_seconds=121.0)
        results[29] = replace(results[29], duration_seconds=122.0)

        summary = build_summary(
            BATCH_ID,
            results,
            logs_audit=LogsAudit(qwen_route_hits=50),
            isolation_ok=True,
        )

        self.assertEqual(summary.status, BatchStatus.FAILED)
        self.assertEqual(summary.by_kind["chat"]["succeeded"], 28)
        self.assertEqual(summary.by_kind["chat"]["p95_seconds"], 121.0)

    def test_summary_fails_on_every_hard_failure(self) -> None:
        results = _passing_results()
        results[0] = _sample_result(
            SampleKind.CHAT,
            1,
            success=False,
            false_success=True,
            fail_closed=False,
        )

        summary = build_summary(
            BATCH_ID,
            results,
            logs_audit=LogsAudit(mock_hits=1, forbidden_route_hits=1),
            isolation_ok=False,
        )

        self.assertEqual(summary.status, BatchStatus.FAILED)
        self.assertIn("false_success", summary.hard_failures)
        self.assertIn("fail_closed", summary.hard_failures)
        self.assertIn("mock_detected", summary.hard_failures)
        self.assertIn("forbidden_route", summary.hard_failures)
        self.assertIn("tenant_isolation_breach", summary.hard_failures)

    def test_incomplete_or_interrupted_batch_is_aborted(self) -> None:
        summary = build_summary(
            BATCH_ID,
            [_sample_result(SampleKind.CHAT, 1)],
            logs_audit=LogsAudit(),
            isolation_ok=False,
            aborted_error="KeyboardInterrupt",
        )

        self.assertEqual(summary.status, BatchStatus.ABORTED)
        self.assertEqual(summary.completed_samples, 1)
        self.assertEqual(summary.aborted_error, "KeyboardInterrupt")


class R3EvidenceWriterTests(unittest.TestCase):
    def test_recorder_writes_public_json_and_refuses_existing_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = replace(
                _sample_result(SampleKind.CHAT, 1),
                error="Bearer super-secret token=abc password=hunter2",
            )
            summary = build_summary(
                BATCH_ID,
                [result],
                logs_audit=LogsAudit(qwen_route_hits=1),
                isolation_ok=False,
                aborted_error="stopped authorization=private-value",
            )
            recorder = BatchRecorder(root, BATCH_ID)

            recorder.start()
            recorder.append(result)
            recorder.finalize(summary, summary.logs_audit)

            batch_dir = root / BATCH_ID
            sample_text = (batch_dir / "samples.jsonl").read_text("utf-8")
            sample_payload = json.loads(sample_text)
            summary_text = (batch_dir / "summary.json").read_text("utf-8")
            summary_payload = json.loads(summary_text)
            logs_payload = json.loads(
                (batch_dir / "logs-audit.json").read_text("utf-8")
            )
            self.assertEqual(sample_payload["kind"], "chat")
            self.assertEqual(summary_payload["status"], "aborted")
            self.assertEqual(logs_payload["qwen_route_hits"], 1)
            for text in (sample_text, summary_text):
                self.assertNotIn("super-secret", text)
                self.assertNotIn("hunter2", text)
                self.assertNotIn("private-value", text)
                self.assertNotIn("reasoning", text.lower())
                self.assertNotIn("system_prompt", text.lower())
            with self.assertRaises(FileExistsError):
                BatchRecorder(root, BATCH_ID).start()

    def test_recorder_cannot_append_after_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = BatchRecorder(Path(directory), BATCH_ID)
            result = _sample_result(SampleKind.CHAT, 1)
            recorder.start()
            recorder.append(result)
            recorder.finalize(
                build_summary(
                    BATCH_ID,
                    [result],
                    logs_audit=LogsAudit(),
                    isolation_ok=False,
                    aborted_error="stopped",
                ),
                LogsAudit(),
            )

            with self.assertRaises(RuntimeError):
                recorder.append(result)
            with self.assertRaises(RuntimeError):
                recorder.finalize(
                    build_summary(
                        BATCH_ID,
                        [result],
                        logs_audit=LogsAudit(),
                        isolation_ok=False,
                        aborted_error="stopped",
                    ),
                    LogsAudit(),
                )

    def test_markdown_contains_metrics_but_not_raw_secret(self) -> None:
        summary = build_summary(
            BATCH_ID,
            [],
            logs_audit=LogsAudit(mock_hits=1),
            isolation_ok=False,
            aborted_error="password=plain-secret",
        )

        report = render_markdown_report(summary)

        self.assertIn("状态：`aborted`", report)
        self.assertIn("MockLLM 命中：1", report)
        self.assertNotIn("plain-secret", report)
        self.assertNotIn("reasoning", report.lower())


class R3ChatTests(unittest.TestCase):
    def _api(
        self,
        *,
        sse_final: str,
        terminal_status: str,
        persisted_final: str,
        assistant_final: str,
        error: str = "",
        include_done: bool = True,
        include_final: bool = True,
        include_checkpoint: bool = True,
        include_tool_call: bool = False,
    ) -> tuple[ProductApiClient, list[tuple[str, str]]]:
        calls: list[tuple[str, str]] = []
        run_id = "a" * 32
        conversation_id = "b" * 32

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.method == "POST" and request.url.path.endswith(
                "/stream/agents/run"
            ):
                payload = json.loads(request.content)
                self.assertEqual(payload["tool_mode"], "none")
                self.assertEqual(payload["capabilities"], [])
                chunks = [
                    "event: started\n"
                    f'data: {{"run_id":"{run_id}",'
                    f'"conversation_id":"{conversation_id}",'
                    '"route":"chat_no_tools"}\n\n'
                ]
                if include_tool_call:
                    chunks.append(
                        'event: tool_call\ndata: {"kind":"tool_call","tool":"echo"}\n\n'
                    )
                if include_final:
                    chunks.append(
                        "event: final\n"
                        f'data: {{"kind":"final","content":"{sse_final}"}}\n\n'
                    )
                if error:
                    chunks.append(
                        f'event: error\ndata: {{"error":"{error}",'
                        f'"run_id":"{run_id}"}}\n\n'
                    )
                if include_done:
                    chunks.append(f'event: done\ndata: {{"run_id":"{run_id}"}}\n\n')
                chunks.append("event: end\ndata: {}\n\n")
                return httpx.Response(
                    200,
                    text="".join(chunks),
                    headers={"content-type": "text/event-stream"},
                )
            if request.url.path.endswith(f"/runs/{run_id}"):
                return httpx.Response(
                    200,
                    json={
                        "task": {
                            "task_id": run_id,
                            "status": terminal_status,
                            "input": {
                                "tool_mode": "none",
                                "route": "chat_no_tools",
                            },
                            "result": {
                                "final_answer": persisted_final,
                                "events": [],
                            },
                            "error": error,
                        }
                    },
                )
            if request.url.path.endswith("/checkpoints"):
                checkpoints = [{"checkpoint_id": "cp-1"}] if include_checkpoint else []
                return httpx.Response(
                    200,
                    json={"total": len(checkpoints), "checkpoints": checkpoints},
                )
            if request.url.path.endswith(f"/conversations/{conversation_id}/messages"):
                return httpx.Response(
                    200,
                    json={
                        "messages": [
                            {"role": "user", "content": "prompt"},
                            {"role": "assistant", "content": assistant_final},
                        ]
                    },
                )
            raise AssertionError(str(request.url))

        api = ProductApiClient(
            "http://xagent.test/api/v1",
            token="memory-only-token",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        return api, calls

    def test_chat_reads_sse_runtime_conversation_and_checkpoint_once(self) -> None:
        spec = build_sample_plan(BATCH_ID)[0]
        api, calls = self._api(
            sse_final=spec.marker,
            terminal_status="succeeded",
            persisted_final=spec.marker,
            assistant_final=spec.marker,
        )

        result = run_chat_sample(api, spec, model="qwen3:4b")

        self.assertTrue(result.success)
        self.assertTrue(result.exact_match)
        self.assertEqual(result.route, "chat_no_tools")
        self.assertEqual(result.tool_mode, "none")
        self.assertEqual(result.checkpoint_id, "cp-1")
        self.assertEqual(result.tool_call_count, 0)
        self.assertEqual(
            calls.count(("POST", "/api/v1/stream/agents/run")),
            1,
        )
        with self.assertRaises(RuntimeError):
            run_chat_sample(api, spec, model="qwen3:4b")

    def test_chat_empty_response_failure_is_truthful_and_fail_closed(self) -> None:
        spec = build_sample_plan(BATCH_ID)[0]
        api, calls = self._api(
            sse_final="",
            terminal_status="failed",
            persisted_final="",
            assistant_final="",
            error="model_empty_response_after_retry",
            include_done=False,
            include_final=False,
            include_checkpoint=False,
        )

        result = run_chat_sample(api, spec, model="qwen3:4b")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "model_empty_response")
        self.assertEqual(result.terminal_status, "failed")
        self.assertTrue(result.fail_closed)
        self.assertFalse(result.false_success)
        self.assertEqual(
            calls.count(("POST", "/api/v1/stream/agents/run")),
            1,
        )

    def test_chat_succeeded_with_wrong_final_is_false_success(self) -> None:
        spec = build_sample_plan(BATCH_ID)[0]
        api, _ = self._api(
            sse_final="WRONG",
            terminal_status="succeeded",
            persisted_final="WRONG",
            assistant_final="WRONG",
            include_tool_call=True,
        )

        result = run_chat_sample(api, spec, model="qwen3:4b")

        self.assertFalse(result.success)
        self.assertFalse(result.exact_match)
        self.assertTrue(result.false_success)
        self.assertEqual(result.error_code, "false_success")
        self.assertEqual(result.tool_call_count, 1)


class R3SchedulerTests(unittest.TestCase):
    def _api(
        self,
        *,
        terminal_status: str,
        result_text: str,
        error: str = "",
        toggle_status: int = 200,
    ) -> tuple[ProductApiClient, list[tuple[str, str]], list[dict[str, object]]]:
        calls: list[tuple[str, str]] = []
        bodies: list[dict[str, object]] = []
        job_id = "c" * 12
        scheduler_run_id = "d" * 32
        agent_run_id = "e" * 32

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.content:
                bodies.append(json.loads(request.content))
            if request.method == "POST" and request.url.path.endswith(
                "/scheduler/jobs"
            ):
                payload = bodies[-1]
                self.assertEqual(payload["interval_seconds"], 86_400)
                self.assertEqual(payload["max_retries"], 0)
                return httpx.Response(
                    200,
                    json={"job_id": job_id, "enabled": True},
                )
            if request.method == "POST" and request.url.path.endswith(
                f"/scheduler/jobs/{job_id}/run"
            ):
                self.assertEqual(bodies[-1], {"confirm_job_id": job_id})
                return httpx.Response(
                    200,
                    json={
                        "run_id": scheduler_run_id,
                        "job_id": job_id,
                        "status": "pending",
                        "attempt": 1,
                    },
                )
            if request.method == "GET" and request.url.path.endswith(
                f"/scheduler/jobs/{job_id}/runs"
            ):
                return httpx.Response(
                    200,
                    json={
                        "runs": [
                            {
                                "run_id": scheduler_run_id,
                                "job_id": job_id,
                                "status": terminal_status,
                                "attempt": 1,
                                "agent_run_id": agent_run_id,
                                "result": result_text,
                                "error": error,
                            }
                        ]
                    },
                )
            if request.method == "PATCH" and request.url.path.endswith(
                f"/scheduler/jobs/{job_id}/toggle"
            ):
                self.assertEqual(
                    bodies[-1], {"confirm_job_id": job_id, "enabled": False}
                )
                return httpx.Response(
                    toggle_status,
                    json={"job_id": job_id, "enabled": False},
                )
            if request.method == "GET" and request.url.path.endswith("/scheduler/jobs"):
                return httpx.Response(
                    200,
                    json={"jobs": [{"job_id": job_id, "enabled": False}]},
                )
            raise AssertionError(str(request.url))

        api = ProductApiClient(
            "http://xagent.test/api/v1",
            token="memory-only-token",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        return api, calls, bodies

    def test_scheduler_runs_attempt_one_once_and_pauses(self) -> None:
        spec = build_sample_plan(BATCH_ID)[30]
        api, calls, _ = self._api(
            terminal_status="succeeded",
            result_text=spec.marker,
        )

        result = run_scheduler_sample(
            api,
            spec,
            model="qwen3:4b",
            sleep=lambda _seconds: None,
        )

        job_path = f"/api/v1/scheduler/jobs/{'c' * 12}"
        self.assertTrue(result.success)
        self.assertEqual(result.run_id, "e" * 32)
        self.assertEqual(result.task_id, "d" * 32)
        self.assertEqual(result.job_id, "c" * 12)
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(calls.count(("POST", "/api/v1/scheduler/jobs")), 1)
        self.assertEqual(calls.count(("POST", f"{job_path}/run")), 1)
        self.assertEqual(calls.count(("PATCH", f"{job_path}/toggle")), 1)
        with self.assertRaises(RuntimeError):
            run_scheduler_sample(
                api,
                spec,
                model="qwen3:4b",
                sleep=lambda _seconds: None,
            )

    def test_scheduler_failure_is_fail_closed_and_still_paused(self) -> None:
        spec = build_sample_plan(BATCH_ID)[30]
        api, calls, _ = self._api(
            terminal_status="failed",
            result_text="",
            error="provider failed",
        )

        result = run_scheduler_sample(
            api,
            spec,
            model="qwen3:4b",
            sleep=lambda _seconds: None,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "scheduler_terminal_error")
        self.assertTrue(result.fail_closed)
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(
            calls.count(("PATCH", f"/api/v1/scheduler/jobs/{'c' * 12}/toggle")),
            1,
        )

    def test_scheduler_cleanup_failure_cannot_be_success(self) -> None:
        spec = build_sample_plan(BATCH_ID)[30]
        api, _, _ = self._api(
            terminal_status="succeeded",
            result_text=spec.marker,
            toggle_status=409,
        )

        result = run_scheduler_sample(
            api,
            spec,
            model="qwen3:4b",
            sleep=lambda _seconds: None,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "cleanup_failed")
        self.assertFalse(result.cleanup_ok)


class R3FileWriteTests(unittest.TestCase):
    def _api(
        self,
        spec,
        *,
        patch_text: str | None = None,
        reject_status: int = 200,
        terminal_status: str = "succeeded",
        development_status: str = "awaiting_review",
        error: str = "",
    ) -> tuple[
        ProductApiClient,
        list[tuple[str, str]],
        list[list[str]],
        object,
    ]:
        calls: list[tuple[str, str]] = []
        shell_calls: list[list[str]] = []
        task_id = "d" * 32
        result_commit = "f" * 40
        rejected = False
        expected_patch = (
            patch_text
            if patch_text is not None
            else (
                f"diff --git a/{spec.filename} b/{spec.filename}\n"
                f"+++ b/{spec.filename}\n+{spec.marker}\n"
            )
        )

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal rejected
            calls.append((request.method, request.url.path))
            if request.method == "POST" and request.url.path.endswith(
                "/agents/parallel-run"
            ):
                payload = json.loads(request.content)
                self.assertEqual(payload["tasks"][0]["capabilities"], ["file_write"])
                self.assertTrue(payload["use_worktrees"])
                self.assertIn(spec.filename, payload["tasks"][0]["goal"])
                self.assertIn(spec.marker, payload["tasks"][0]["goal"])
                return httpx.Response(
                    200,
                    json={
                        "run_id": "parent-run",
                        "status": terminal_status,
                        "sub_results": [
                            {
                                "run_id": "parent-run_sub0",
                                "status": terminal_status,
                                "steps": 2,
                                "error": error,
                                "isolated": True,
                                "diff_stat": f" {spec.filename} | 1 +",
                                "diff": f"+{spec.marker}",
                                "development_task_id": task_id,
                                "development_task_status": development_status,
                            }
                        ],
                    },
                )
            if request.method == "GET" and request.url.path.endswith(
                f"/development-tasks/{task_id}"
            ):
                return httpx.Response(
                    200,
                    json={
                        "task_id": task_id,
                        "status": "rejected" if rejected else development_status,
                        "result_commit": result_commit,
                        "diff_stat": f" {spec.filename} | 1 +",
                        "error": "",
                    },
                )
            if request.method == "GET" and request.url.path.endswith(
                f"/development-tasks/{task_id}/patch"
            ):
                return httpx.Response(
                    200,
                    json={"task_id": task_id, "patch": expected_patch},
                )
            if request.method == "POST" and request.url.path.endswith(
                f"/development-tasks/{task_id}/reject"
            ):
                self.assertEqual(
                    json.loads(request.content), {"confirm_task_id": task_id}
                )
                if reject_status == 200:
                    rejected = True
                return httpx.Response(
                    reject_status,
                    json={
                        "task_id": task_id,
                        "status": "rejected" if rejected else "awaiting_review",
                    },
                )
            raise AssertionError(str(request.url))

        def shell_runner(
            args: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            self.assertNotIn("shell", kwargs)
            shell_calls.append(args)
            stdout = ""
            if args[-3:-1] == ["--list", f"agent/{task_id}"]:
                stdout = ""
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=stdout, stderr=""
            )

        api = ProductApiClient(
            "http://xagent.test/api/v1",
            token="memory-only-token",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        return api, calls, shell_calls, shell_runner

    def test_file_write_verifies_patch_commit_and_reject_cleanup(self) -> None:
        spec = build_sample_plan(BATCH_ID)[40]
        api, calls, shell_calls, shell_runner = self._api(spec)
        compose = ComposeTarget(
            compose_file=Path("deploy/compose/docker-compose.yml"),
            env_file=Path("deploy/compose/r2.env.local"),
            project_name="xagent-r2",
        )

        result = run_file_write_sample(
            api,
            spec,
            model="qwen3:4b",
            compose=compose,
            shell_runner=shell_runner,
        )

        expected_patch = (
            f"diff --git a/{spec.filename} b/{spec.filename}\n"
            f"+++ b/{spec.filename}\n+{spec.marker}\n"
        )
        task_path = f"/api/v1/development-tasks/{'d' * 32}"
        self.assertTrue(result.success)
        self.assertTrue(result.exact_match)
        self.assertEqual(result.artifact_count, 4)
        self.assertEqual(
            result.patch_sha256,
            hashlib.sha256(expected_patch.encode()).hexdigest(),
        )
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(calls.count(("POST", "/api/v1/agents/parallel-run")), 1)
        self.assertEqual(calls.count(("POST", f"{task_path}/reject")), 1)
        self.assertTrue(
            any("/data/.xagent-worktrees/" in " ".join(call) for call in shell_calls)
        )
        self.assertTrue(
            any("cat-file" in call and "shell" not in call for call in shell_calls)
        )
        with self.assertRaises(RuntimeError):
            run_file_write_sample(
                api,
                spec,
                model="qwen3:4b",
                compose=compose,
                shell_runner=shell_runner,
            )

    def test_file_write_patch_mismatch_is_false_success_then_rejected(self) -> None:
        spec = build_sample_plan(BATCH_ID)[40]
        api, calls, _, shell_runner = self._api(
            spec, patch_text="diff without expected marker"
        )

        result = run_file_write_sample(
            api,
            spec,
            model="qwen3:4b",
            compose=ComposeTarget(Path("compose.yml"), Path("env"), "xagent-r2"),
            shell_runner=shell_runner,
        )

        self.assertFalse(result.success)
        self.assertTrue(result.false_success)
        self.assertEqual(result.error_code, "patch_mismatch")
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(
            calls.count(("POST", f"/api/v1/development-tasks/{'d' * 32}/reject")),
            1,
        )

    def test_file_write_reject_failure_cannot_be_success(self) -> None:
        spec = build_sample_plan(BATCH_ID)[40]
        api, calls, _, shell_runner = self._api(spec, reject_status=409)

        result = run_file_write_sample(
            api,
            spec,
            model="qwen3:4b",
            compose=ComposeTarget(Path("compose.yml"), Path("env"), "xagent-r2"),
            shell_runner=shell_runner,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "cleanup_failed")
        self.assertFalse(result.cleanup_ok)
        self.assertEqual(
            calls.count(("POST", f"/api/v1/development-tasks/{'d' * 32}/reject")),
            1,
        )

    def test_file_write_product_failure_is_fail_closed(self) -> None:
        spec = build_sample_plan(BATCH_ID)[40]
        api, calls, _, shell_runner = self._api(
            spec,
            terminal_status="failed",
            development_status="failed",
            error="model_empty_response_after_retry",
        )

        result = run_file_write_sample(
            api,
            spec,
            model="qwen3:4b",
            compose=ComposeTarget(Path("compose.yml"), Path("env"), "xagent-r2"),
            shell_runner=shell_runner,
        )

        self.assertFalse(result.success)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.error_code, "model_empty_response")
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(
            calls.count(("POST", f"/api/v1/development-tasks/{'d' * 32}/reject")),
            0,
        )


class R3PreflightTests(unittest.TestCase):
    service_names = (
        "api",
        "worker",
        "web",
        "postgres",
        "redis",
        "qdrant",
        "platform-mcp",
        "prometheus",
        "grafana",
    )

    def _run(
        self,
        *,
        dirty_git: bool = False,
        unhealthy_service: str = "",
        protected_healthy: bool = True,
        deep_redis: str = "healthy",
        pong: bool = True,
        model: str = "ollama/qwen3:4b",
        configured_model: str = "qwen3:4b",
        busy_probe: str = "",
        healthless_observability: bool = False,
        observability_ok: bool = True,
        celery_log_prefix: bool = False,
    ) -> tuple[PreflightSnapshot, list[list[str]]]:
        calls: list[list[str]] = []
        services = [
            {
                "Service": name,
                "State": "running",
                "Health": (
                    ""
                    if healthless_observability and name in {"prometheus", "grafana"}
                    else "unhealthy"
                    if name == unhealthy_service
                    else "healthy"
                ),
                "ID": f"id-{name}",
            }
            for name in self.service_names
        ]
        protected = [
            {
                "Id": f"protected-{name}",
                "Name": f"/{name}",
                "State": {
                    "Status": "running",
                    "Health": {
                        "Status": "healthy" if protected_healthy else "unhealthy"
                    },
                },
            }
            for name in ("aicg-minio", "aicg-postgres")
        ]

        def shell_runner(
            args: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            stdout = ""
            returncode = 0
            if args[:2] == ["git", "status"]:
                stdout = " M dirty.txt\n" if dirty_git else ""
            elif args[:2] == ["docker", "inspect"]:
                stdout = "\n".join(json.dumps(item) for item in protected)
            elif "ps" in args and "--format" in args:
                stdout = json.dumps(services)
            elif "get_llm_client" in " ".join(args):
                stdout = f"{model}\n{configured_model}\n"
            elif "prometheus:9090" in " ".join(args):
                stdout = "healthy\n" if observability_ok else ""
                returncode = 0 if observability_ok else 1
            elif "inspect" in args and "ping" in args:
                stdout = json.dumps({"celery@worker": {"ok": "pong"}} if pong else {})
            elif "inspect" in args:
                probe = next(
                    name for name in ("active", "reserved", "scheduled") if name in args
                )
                stdout = json.dumps(
                    {"celery@worker": [{}] if probe == busy_probe else []}
                )
            if celery_log_prefix and "celery" in args and "inspect" in args and stdout:
                stdout = f"celery initialized\n{stdout}"
            return subprocess.CompletedProcess(
                args=args, returncode=returncode, stdout=stdout, stderr=""
            )

        def health_handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "healthy" if deep_redis == "healthy" else "degraded",
                    "checks": {
                        "database": {"status": "healthy"},
                        "redis": {"status": deep_redis},
                        "qdrant": {"status": "healthy"},
                    },
                },
            )

        snapshot = run_preflight(
            repo_root=Path("."),
            compose=ComposeTarget(Path("compose.yml"), Path("env"), "xagent-r2"),
            health_url="http://xagent.test/health/deep",
            shell_runner=shell_runner,
            health_client=httpx.Client(transport=httpx.MockTransport(health_handler)),
        )
        return snapshot, calls

    def test_preflight_passes_with_read_only_commands(self) -> None:
        snapshot, calls = self._run()

        self.assertTrue(snapshot.passed)
        self.assertEqual(snapshot.model, "qwen3:4b")
        self.assertEqual(set(snapshot.service_ids), set(self.service_names))
        self.assertEqual(
            set(snapshot.protected_container_ids), {"aicg-minio", "aicg-postgres"}
        )
        forbidden = {"down", "up", "restart", "rm", "prune", "pause", "unpause"}
        self.assertFalse(any(forbidden.intersection(call) for call in calls))

    def test_preflight_rejects_dirty_git_before_docker(self) -> None:
        snapshot, calls = self._run(dirty_git=True)

        self.assertFalse(snapshot.passed)
        self.assertEqual(snapshot.code, "git_dirty")
        self.assertEqual(len(calls), 1)

    def test_preflight_rejects_unhealthy_service_or_protected_container(self) -> None:
        with self.subTest("service"):
            snapshot, _ = self._run(unhealthy_service="grafana")
            self.assertEqual(snapshot.code, "service_unhealthy")
        with self.subTest("protected"):
            snapshot, _ = self._run(protected_healthy=False)
            self.assertEqual(snapshot.code, "protected_container_unhealthy")

    def test_preflight_rejects_health_model_pong_and_busy_worker(self) -> None:
        cases = (
            ({"deep_redis": "degraded"}, "deep_health_failed"),
            ({"pong": False}, "worker_pong_failed"),
            ({"model": "ollama/qwen2.5:7b"}, "model_mismatch"),
            ({"configured_model": "qwen2.5:7b"}, "model_mismatch"),
            ({"busy_probe": "reserved"}, "worker_not_idle"),
        )
        for kwargs, code in cases:
            with self.subTest(code=code, kwargs=kwargs):
                snapshot, _ = self._run(**kwargs)
                self.assertFalse(snapshot.passed)
                self.assertEqual(snapshot.code, code)

    def test_preflight_accepts_healthless_observability_with_live_endpoints(
        self,
    ) -> None:
        snapshot, _ = self._run(
            healthless_observability=True,
            celery_log_prefix=True,
        )

        self.assertTrue(snapshot.passed)

        failed, _ = self._run(
            healthless_observability=True,
            observability_ok=False,
        )
        self.assertFalse(failed.passed)
        self.assertEqual(failed.code, "service_unhealthy")


class R3LogsTests(unittest.TestCase):
    def test_log_audit_returns_counts_only(self) -> None:
        audit = audit_logs(
            "MockLLM\nTraceback (most recent call last)\n"
            "qwen3:4b qwen3:4b\n/api/v1/creative\n/api/v1/media/tasks"
        )

        self.assertEqual(audit.mock_hits, 1)
        self.assertEqual(audit.traceback_hits, 1)
        self.assertEqual(audit.qwen_route_hits, 2)
        self.assertEqual(audit.forbidden_route_hits, 2)
        self.assertEqual(
            set(audit.to_public_dict()),
            {"mock_hits", "forbidden_route_hits", "traceback_hits", "qwen_route_hits"},
        )


class R3BatchExecutionTests(unittest.TestCase):
    def test_execution_is_strictly_serial_and_does_not_replace_failures(self) -> None:
        seen: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            recorder = BatchRecorder(Path(directory), BATCH_ID)
            recorder.start()

            def executor(spec) -> SampleResult:
                seen.append(spec.sample_id)
                return _sample_result(
                    spec.kind,
                    spec.index,
                    success=spec.sample_id != "chat-003",
                    fail_closed=True if spec.sample_id == "chat-003" else None,
                )

            outcome = execute_sample_plan(
                build_sample_plan(BATCH_ID), recorder, executor
            )

            self.assertIsInstance(outcome, ExecutionOutcome)
            self.assertEqual(
                seen, [item.sample_id for item in build_sample_plan(BATCH_ID)]
            )
            self.assertEqual(len(seen), 50)
            self.assertEqual(len(set(seen)), 50)
            self.assertEqual(len(outcome.results), 50)
            self.assertFalse(outcome.results[2].success)
            self.assertEqual(outcome.aborted_error, "")
            self.assertTrue(
                all(
                    item.cleanup_ok
                    for item in outcome.results
                    if item.kind != SampleKind.CHAT
                )
            )
            lines = recorder.samples_path.read_text("utf-8").splitlines()
            self.assertEqual(len(lines), 50)

    def test_execution_interrupts_without_resuming_or_submitting_more(self) -> None:
        seen: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = BatchRecorder(root, BATCH_ID)
            recorder.start()

            def executor(spec) -> SampleResult:
                seen.append(spec.sample_id)
                if len(seen) == 3:
                    raise KeyboardInterrupt
                return _sample_result(spec.kind, spec.index)

            outcome = execute_sample_plan(
                build_sample_plan(BATCH_ID), recorder, executor
            )

            self.assertEqual(seen, ["chat-001", "chat-002", "chat-003"])
            self.assertEqual(len(outcome.results), 2)
            self.assertIn("KeyboardInterrupt", outcome.aborted_error)
            self.assertEqual(
                len(recorder.samples_path.read_text("utf-8").splitlines()), 2
            )
            summary = build_summary(
                BATCH_ID,
                outcome.results,
                logs_audit=LogsAudit(),
                isolation_ok=False,
                aborted_error=outcome.aborted_error,
            )
            self.assertEqual(summary.status, BatchStatus.ABORTED)
            with self.assertRaises(FileExistsError):
                BatchRecorder(root, BATCH_ID).start()


class R3IsolationTests(unittest.TestCase):
    def _results_with_anchors(self) -> list[SampleResult]:
        results = _passing_results()
        results[0] = replace(
            results[0],
            run_id="r" * 32,
            checkpoint_id="c" * 32,
        )
        results[40] = replace(
            results[40],
            development_task_id="d" * 32,
        )
        return results

    def _api(self, statuses: dict[str, int]) -> ProductApiClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(statuses[request.url.path], json={"detail": "hidden"})

        return ProductApiClient(
            "http://xagent.test/api/v1",
            token="second-tenant-memory-token",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    def test_second_tenant_cannot_read_first_tenant_anchors(self) -> None:
        statuses = {
            f"/api/v1/runs/{'r' * 32}": 404,
            f"/api/v1/checkpoints/{'c' * 32}": 403,
            f"/api/v1/development-tasks/{'d' * 32}": 404,
        }

        result = run_tenant_isolation_probe(
            self._api(statuses), self._results_with_anchors()
        )

        self.assertIsInstance(result, IsolationProbeResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.error_code, "")

    def test_readable_anchor_is_a_tenant_isolation_breach(self) -> None:
        statuses = {
            f"/api/v1/runs/{'r' * 32}": 200,
            f"/api/v1/checkpoints/{'c' * 32}": 403,
            f"/api/v1/development-tasks/{'d' * 32}": 404,
        }

        result = run_tenant_isolation_probe(
            self._api(statuses), self._results_with_anchors()
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "tenant_isolation_breach")

    def test_missing_anchor_is_a_harness_error(self) -> None:
        result = run_tenant_isolation_probe(
            self._api({}),
            _passing_results(),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "harness_error")


class R3CliTests(unittest.TestCase):
    def _batch_outcome(self, status: BatchStatus, root: Path) -> BatchRunOutcome:
        if status is BatchStatus.PASSED:
            results = _passing_results()
            aborted_error = ""
        elif status is BatchStatus.FAILED:
            results = _passing_results()
            for index in (0, 1):
                results[index] = replace(
                    results[index],
                    success=False,
                    exact_match=False,
                    terminal_status="failed",
                    fail_closed=True,
                )
            aborted_error = ""
        else:
            results = []
            aborted_error = "KeyboardInterrupt"
        summary = build_summary(
            BATCH_ID,
            results,
            logs_audit=LogsAudit(),
            isolation_ok=status is not BatchStatus.ABORTED,
            aborted_error=aborted_error,
        )
        return BatchRunOutcome(
            batch_id=BATCH_ID,
            summary=summary,
            directory=root / BATCH_ID,
            report_path=root / "report.md",
        )

    def test_batch_id_has_fixed_utc_random_format(self) -> None:
        self.assertRegex(generate_batch_id(), r"^\d{8}T\d{6}Z-[a-f0-9]{6}$")

    def test_cli_maps_passed_failed_and_aborted_exit_codes(self) -> None:
        expected = {
            BatchStatus.PASSED: 0,
            BatchStatus.FAILED: 1,
            BatchStatus.ABORTED: 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for status, exit_code in expected.items():
                with self.subTest(status=status):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        actual = cli(
                            ["--output-root", str(root)],
                            preflight_runner=lambda **_kwargs: PreflightSnapshot(
                                passed=True,
                                code="passed",
                                error="",
                                model="qwen3:4b",
                            ),
                            batch_runner=lambda **_kwargs: self._batch_outcome(
                                status, root
                            ),
                        )
                    self.assertEqual(actual, exit_code)
                    output = stdout.getvalue()
                    self.assertIn(f"batch_id={BATCH_ID}", output)
                    self.assertIn(f"status={status.value}", output)
                    self.assertNotIn("token", output.lower())
                    self.assertNotIn("password", output.lower())

    def test_cli_preflight_failure_and_preflight_only_never_start_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            calls = 0

            def batch_runner(**_kwargs) -> BatchRunOutcome:
                nonlocal calls
                calls += 1
                raise AssertionError("batch must not start")

            failed_stdout = io.StringIO()
            with redirect_stdout(failed_stdout):
                failed_code = cli(
                    ["--output-root", str(root)],
                    preflight_runner=lambda **_kwargs: PreflightSnapshot(
                        passed=False, code="git_dirty", error="dirty"
                    ),
                    batch_runner=batch_runner,
                )
            self.assertEqual(failed_code, 2)
            self.assertIn("preflight=git_dirty", failed_stdout.getvalue())

            passed_stdout = io.StringIO()
            with redirect_stdout(passed_stdout):
                passed_code = cli(
                    ["--output-root", str(root), "--preflight-only"],
                    preflight_runner=lambda **_kwargs: PreflightSnapshot(
                        passed=True, code="passed", error="", model="qwen3:4b"
                    ),
                    batch_runner=batch_runner,
                )
            self.assertEqual(passed_code, 0)
            self.assertEqual(passed_stdout.getvalue().strip(), "preflight=passed")
            self.assertEqual(calls, 0)
            self.assertFalse(root.exists())


class R3BatchOrchestrationTests(unittest.TestCase):
    def test_batch_registers_in_memory_runs_once_and_finalizes_evidence(self) -> None:
        events: list[str] = []
        registration_payloads: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path.endswith("/auth/register"):
                body = json.loads(request.content)
                registration_payloads.append(body)
                events.append(f"register:{body['tenant_id']}")
                return httpx.Response(
                    200,
                    json={
                        "access_token": f"memory-token-{len(registration_payloads)}",
                        "tenant_id": body["tenant_id"],
                    },
                )
            if request.method == "GET" and request.url.path.endswith(
                f"/runs/{'r' * 32}"
            ):
                return httpx.Response(404, json={"detail": "hidden"})
            if request.method == "GET" and request.url.path.endswith(
                f"/checkpoints/{'c' * 32}"
            ):
                return httpx.Response(403, json={"detail": "hidden"})
            if request.method == "GET" and request.url.path.endswith(
                f"/development-tasks/{'d' * 32}"
            ):
                return httpx.Response(404, json={"detail": "hidden"})
            raise AssertionError(str(request.url))

        def api_factory(base_url: str) -> ProductApiClient:
            return ProductApiClient(
                base_url,
                client=httpx.Client(transport=httpx.MockTransport(handler)),
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "output"
            report_path = root / "report.md"

            def executor(spec) -> SampleResult:
                self.assertTrue((output_root / BATCH_ID / "samples.jsonl").exists())
                events.append(f"sample:{spec.sample_id}")
                result = _sample_result(spec.kind, spec.index)
                if spec.sample_id == "chat-001":
                    result = replace(
                        result,
                        run_id="r" * 32,
                        checkpoint_id="c" * 32,
                    )
                if spec.sample_id == "file-write-001":
                    result = replace(result, development_task_id="d" * 32)
                return result

            preflight = PreflightSnapshot(
                passed=True,
                code="passed",
                error="",
                model="qwen3:4b",
                service_ids={"api": "api-id"},
                protected_container_ids={"aicg-minio": "minio-id"},
            )
            outcome = run_reliability_batch(
                preflight=preflight,
                api_base_url="http://xagent.test/api/v1",
                compose=ComposeTarget(Path("compose.yml"), Path("env"), "xagent-r2"),
                output_root=output_root,
                report_path=report_path,
                repo_root=Path("."),
                api_factory=api_factory,
                batch_id_factory=lambda: BATCH_ID,
                sample_executor=executor,
                identity_reader=lambda: (
                    preflight.service_ids,
                    preflight.protected_container_ids,
                ),
                logs_reader=lambda _since: LogsAudit(qwen_route_hits=50),
            )

            self.assertEqual(outcome.summary.status, BatchStatus.PASSED)
            self.assertEqual(len(registration_payloads), 2)
            self.assertEqual(len(registration_payloads[0]["password"]), 44)
            self.assertEqual(len(registration_payloads[1]["password"]), 44)
            self.assertTrue(events[0].startswith("register:r3-reliability-"))
            self.assertEqual(
                events[1:51],
                [f"sample:{item.sample_id}" for item in build_sample_plan(BATCH_ID)],
            )
            self.assertTrue(events[51].startswith("register:r3-reliability-isolation-"))
            self.assertEqual(
                len(
                    (outcome.directory / "samples.jsonl")
                    .read_text("utf-8")
                    .splitlines()
                ),
                50,
            )
            self.assertTrue((outcome.directory / "summary.json").is_file())
            self.assertTrue((outcome.directory / "logs-audit.json").is_file())
            self.assertTrue(report_path.is_file())
            evidence = "\n".join(
                path.read_text("utf-8")
                for path in (
                    outcome.directory / "samples.jsonl",
                    outcome.directory / "summary.json",
                    outcome.directory / "logs-audit.json",
                    report_path,
                )
            )
            self.assertNotIn("memory-token", evidence)
            self.assertNotIn(registration_payloads[0]["password"], evidence)


if __name__ == "__main__":
    unittest.main()
