from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import httpx

from scripts.r3_model_reliability import (
    BatchRecorder,
    BatchStatus,
    FailureCode,
    LogsAudit,
    ProductApiClient,
    SampleKind,
    SampleResult,
    build_sample_plan,
    build_summary,
    nearest_rank_percentile,
    render_markdown_report,
    run_chat_sample,
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


if __name__ == "__main__":
    unittest.main()
