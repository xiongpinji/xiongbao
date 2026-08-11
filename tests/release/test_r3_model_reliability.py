from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from scripts.r3_model_reliability import (
    BatchRecorder,
    BatchStatus,
    FailureCode,
    LogsAudit,
    SampleKind,
    SampleResult,
    build_sample_plan,
    build_summary,
    nearest_rank_percentile,
    render_markdown_report,
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


if __name__ == "__main__":
    unittest.main()
