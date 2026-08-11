# X-Agent Web/API R3-A 真实模型可靠性基线实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为当前 Web/API 本地发布候选实现一个不可变、可审计的 50 样本真实 Ollama 基线工具，并用同一批次证明 Chat、Scheduler、file_write 的精确成功率、P95、假成功、fail-closed、清理和租户隔离。

**架构：** 宿主机 Python 工具通过现有 HTTP API 黑盒执行 30 次无工具 Chat、10 次手动 Scheduler 和 10 次隔离 file_write；每个业务入口只提交一次，所有详情读取和清理复用现有 API。工具以白名单字段写入本机 JSONL/JSON，按固定公式生成脱敏报告；生产 API、数据库 schema、模型路由和恢复策略保持不变。

**技术栈：** Python 3.13、`httpx` 0.28、`unittest`/`pytest`、FastAPI SSE、Docker Compose、Ollama `qwen3:4b`、PostgreSQL、Celery Scheduler、Git worktree。

---

## 文件职责

### 创建

- `scripts/r3_model_reliability.py`：枚举、样本计划、结果类型、SSE/API 客户端、三类样本执行器、统计、预检、日志审计和证据写入。
- `scripts/run_r3_model_reliability.py`：薄 CLI 入口，只解析非秘密参数并返回稳定退出码。
- `tests/release/test_r3_model_reliability.py`：纯逻辑、fake HTTP、fake shell 和批次编排合同。
- `docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md`：唯一正式批次生成并人工复核后的脱敏结论。

### 修改

- `.gitignore`：忽略 `output/reliability/` 原始批次证据。
- `docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`：实现开始后增加 R3-A；根据真实批次结果更新为 `REVIEW`、`PARTIAL` 或 `BLOCKED`。

### 明确不修改

- `apps/api/xagent/**`、`apps/web/src/**`、数据库 migration、模型配置和 Compose 服务定义。
- 短剧、媒体、画布、剪辑、Tauri、E2B、多机 HA、付费 provider 和生产发布入口。
- 现有 R2 报告、六张验收截图和历史原始证据。

---

## 固定实现合同

- 正式批次顺序固定为 `chat-001..030`、`scheduler-001..010`、`file-write-001..010`。
- Chat 和 Scheduler prompt 固定为 `请只回复：<marker>`；file_write prompt 固定要求唯一文件名、唯一正文和必须调用 `file_write`。
- `httpx` 不配置 transport retry；同一 `sample_id + business endpoint` 第二次 POST 必须由客户端本地拒绝。
- Chat、Scheduler、file_write 的业务超时分别为 600、600、300 秒；SLO 仍按 120、180、240 秒判断，超阈值但自然完成的样本必须保留真实耗时。
- Scheduler 创建参数固定 `interval_seconds=86400`、`max_retries=0`，并在 `finally` 中禁用。
- `finish_reason` 未由产品公开时固定写 `unknown`，不得从日志或 token 数推断。
- 正式批次目录使用独占创建；已存在的 `batch_id` 不允许续写、覆盖或合并。
- 退出码固定为：`0=passed`、`1=failed`、`2=preflight_failed/aborted`。

---

### 任务 0：计划获批后登记 R3-A Ready 状态

**文件：**
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`

- [ ] **步骤 1：确认计划已获 Owner 接受**

只接受明确的“按此计划执行”指令；计划文档落盘但尚未接受时，不修改任务板、不开始编码。

- [ ] **步骤 2：在 Ready 增加唯一 R3-A 条目**

```markdown
- [R3-A] 真实 Ollama 可靠性基线 | 状态：READY | 设计与逐步 TDD 计划已通过；正式工具、离线门和 50 样本均未开始。
```

同时把 Board Meta 的当前阶段、设计源、R3 计划和最后更新时间改为当前 R3-A 事实；不得改写已完成的 R2 证据。

- [ ] **步骤 3：验证并独立提交任务板状态**

```powershell
git diff --check
git diff -- docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git add docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "docs(任务板): 登记 R3 可靠性基线"
```

预期：只修改任务板；R3-A 为 READY，不是 CLAIMED/REVIEW/DONE。

---

### 任务 1：建立固定样本计划、结果类型和 SLO 纯逻辑

**文件：**
- 创建：`tests/release/test_r3_model_reliability.py`
- 创建：`scripts/r3_model_reliability.py`

- [ ] **步骤 1：先写固定矩阵和 nearest-rank 的失败测试**

在 `tests/release/test_r3_model_reliability.py` 创建：

```python
from __future__ import annotations

import unittest
from dataclasses import replace

from scripts.r3_model_reliability import (
    BatchStatus,
    FailureCode,
    LogsAudit,
    SampleKind,
    SampleResult,
    build_sample_plan,
    build_summary,
    nearest_rank_percentile,
)


class R3PlanAndSummaryTests(unittest.TestCase):
    def test_plan_is_fixed_order_and_has_unique_public_markers(self) -> None:
        plan = build_sample_plan("20260811T010203Z-ab12cd")
        self.assertEqual(len(plan), 50)
        self.assertEqual([item.kind for item in plan[:30]], [SampleKind.CHAT] * 30)
        self.assertEqual([item.kind for item in plan[30:40]], [SampleKind.SCHEDULER] * 10)
        self.assertEqual([item.kind for item in plan[40:]], [SampleKind.FILE_WRITE] * 10)
        self.assertEqual(plan[0].sample_id, "chat-001")
        self.assertEqual(plan[30].sample_id, "scheduler-001")
        self.assertEqual(plan[40].sample_id, "file-write-001")
        self.assertEqual(len({item.marker for item in plan}), 50)
        self.assertEqual(plan[0].marker, "R3-CHAT-20260811T010203Z-ab12cd-001")
        self.assertEqual(
            plan[40].filename,
            "R3_RELIABILITY_20260811T010203Z_ab12cd_001.md",
        )

    def test_nearest_rank_percentile_uses_ceil_rank(self) -> None:
        values = [float(value) for value in range(1, 31)]
        self.assertEqual(nearest_rank_percentile(values, 0.95), 29.0)
        self.assertEqual(nearest_rank_percentile([3.0, 1.0, 2.0], 0.95), 3.0)
        with self.assertRaises(ValueError):
            nearest_rank_percentile([], 0.95)
```

- [ ] **步骤 2：运行测试并确认正确红灯**

运行：

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q
```

预期：收集失败，提示 `scripts.r3_model_reliability` 不存在；不是语法错误或测试发现器错误。

- [ ] **步骤 3：实现最小枚举、计划和结果结构**

在 `scripts/r3_model_reliability.py` 写入以下公共接口：

```python
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
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
```

- [ ] **步骤 4：补齐 SLO 汇总红灯**

在同一测试类增加一个 `_result()` helper 和三组断言：

```python
    def _result(
        self,
        kind: SampleKind,
        index: int,
        *,
        success: bool = True,
        duration: float = 1.0,
        false_success: bool = False,
        fail_closed: bool | None = None,
    ) -> SampleResult:
        batch_id = "20260811T010203Z-ab12cd"
        spec = next(
            item
            for item in build_sample_plan(batch_id)
            if item.kind is kind and item.index == index
        )
        return SampleResult(
            batch_id=batch_id,
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

    def test_summary_passes_only_at_fixed_thresholds(self) -> None:
        results = [self._result(SampleKind.CHAT, index) for index in range(1, 31)]
        results += [self._result(SampleKind.SCHEDULER, index) for index in range(1, 11)]
        results += [self._result(SampleKind.FILE_WRITE, index) for index in range(1, 11)]
        summary = build_summary(
            "20260811T010203Z-ab12cd",
            results,
            logs_audit=LogsAudit(qwen_route_hits=50),
            isolation_ok=True,
        )
        self.assertEqual(summary.status, BatchStatus.PASSED)
        self.assertEqual(summary.by_kind["chat"]["p95_seconds"], 1.0)

    def test_summary_fails_on_threshold_or_any_hard_failure(self) -> None:
        results = [self._result(SampleKind.CHAT, index) for index in range(1, 31)]
        results += [self._result(SampleKind.SCHEDULER, index) for index in range(1, 11)]
        results += [self._result(SampleKind.FILE_WRITE, index) for index in range(1, 11)]
        results[0] = self._result(
            SampleKind.CHAT,
            1,
            success=False,
            fail_closed=False,
        )
        summary = build_summary(
            "20260811T010203Z-ab12cd",
            results,
            logs_audit=LogsAudit(mock_hits=1),
            isolation_ok=False,
        )
        self.assertEqual(summary.status, BatchStatus.FAILED)
        self.assertIn("fail_closed", summary.hard_failures)
        self.assertIn("mock_detected", summary.hard_failures)
        self.assertIn("tenant_isolation_breach", summary.hard_failures)

    def test_incomplete_or_interrupted_batch_is_aborted(self) -> None:
        summary = build_summary(
            "20260811T010203Z-ab12cd",
            [self._result(SampleKind.CHAT, 1)],
            logs_audit=LogsAudit(),
            isolation_ok=False,
            aborted_error="KeyboardInterrupt",
        )
        self.assertEqual(summary.status, BatchStatus.ABORTED)
        self.assertEqual(summary.completed_samples, 1)
```

- [ ] **步骤 5：实现固定阈值汇总并转绿**

在核心模块增加：

```python
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
            "p95_seconds": nearest_rank_percentile(
                [item.duration_seconds for item in items], 0.95
            ) if items else None,
            "success_threshold": SUCCESS_THRESHOLDS[kind],
            "p95_threshold_seconds": P95_THRESHOLDS[kind],
        }
    failures = [item for item in results if not item.success]
    fail_closed = (
        "not_applicable"
        if not failures
        else all(item.fail_closed is True for item in failures)
    )
    hard: list[str] = []
    if any(item.false_success for item in results):
        hard.append("false_success")
    if fail_closed is False:
        hard.append("fail_closed")
    if logs_audit.mock_hits or any(item.mock_detected for item in results):
        hard.append("mock_detected")
    if logs_audit.forbidden_route_hits or any(
        item.forbidden_route_detected for item in results
    ):
        hard.append("forbidden_route")
    if not isolation_ok:
        hard.append("tenant_isolation_breach")
    complete = len(results) == 50 and all(
        by_kind[kind.value]["completed"] == SAMPLE_COUNTS[kind]
        for kind in SampleKind
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
        if slo_ok and not hard
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
        hard_failures=tuple(hard),
        aborted_error=aborted_error,
    )
```

运行：

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q
```

预期：本任务测试全部通过。

- [ ] **步骤 6：独立提交**

```powershell
git add scripts/r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --cached --check
git commit -m "test(可靠性): 锁定 R3 样本与统计合同"
```

---

### 任务 2：建立白名单序列化、不可变目录和脱敏报告

**文件：**
- 修改：`scripts/r3_model_reliability.py`
- 修改：`tests/release/test_r3_model_reliability.py`
- 修改：`.gitignore`

- [ ] **步骤 1：编写输出不可覆盖和秘密不落盘红灯**

增加测试：

```python
import json
import tempfile
from pathlib import Path

from scripts.r3_model_reliability import BatchRecorder, render_markdown_report


class R3EvidenceWriterTests(unittest.TestCase):
    def test_recorder_writes_only_public_fields_and_refuses_existing_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = BatchRecorder(root, "20260811T010203Z-ab12cd")
            recorder.start()
            result = R3PlanAndSummaryTests()._result(SampleKind.CHAT, 1)
            result = replace(result, error="Bearer super-secret token=abc")
            recorder.append(result)
            recorder.finalize(
                build_summary(
                    result.batch_id,
                    [result],
                    logs_audit=LogsAudit(),
                    isolation_ok=False,
                    aborted_error="stopped",
                ),
                LogsAudit(),
            )
            text = (root / result.batch_id / "samples.jsonl").read_text("utf-8")
            self.assertNotIn("super-secret", text)
            self.assertNotIn("reasoning", text.lower())
            with self.assertRaises(FileExistsError):
                BatchRecorder(root, result.batch_id).start()

    def test_markdown_contains_metrics_but_not_raw_error_or_secret(self) -> None:
        summary = build_summary(
            "20260811T010203Z-ab12cd",
            [],
            logs_audit=LogsAudit(),
            isolation_ok=False,
            aborted_error="password=plain-secret",
        )
        report = render_markdown_report(summary)
        self.assertIn("状态：`aborted`", report)
        self.assertNotIn("plain-secret", report)
```

预期红灯：缺少 `to_public_dict`、`BatchRecorder` 和 `render_markdown_report`。

- [ ] **步骤 2：实现白名单输出和独占目录**

只允许 `SampleResult` 已定义字段进入 JSON；任意错误文本先经过：

```python
_SECRET_PATTERNS = (
    re.compile(r"(?i)Bearer\s+[^\s]+"),
    re.compile(r"(?i)(password|token|authorization)\s*[:=]\s*[^\s,;]+"),
)


def sanitize_error(value: str) -> str:
    text = str(value or "")[:1000]
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
```

给 `SampleResult` 增加 `to_public_dict()`，先 `asdict(self)`，把 `kind` 转成字符串并对 `error` 调用 `sanitize_error`。给 `LogsAudit`、`BatchSummary` 增加同样的公开字典方法；报告只读取汇总数字和错误码，不读取原始 provider body、reasoning、system prompt 或 Authorization。

`BatchRecorder` 必须满足：

```python
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
        (self.directory / "summary.json").write_text(
            json.dumps(summary.to_public_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.directory / "logs-audit.json").write_text(
            json.dumps(logs_audit.to_public_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._finalized = True
```

- [ ] **步骤 3：忽略原始结果并验证绿灯**

在 `.gitignore` 的 R2 output 后增加：

```gitignore
output/reliability/
```

运行：

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q
git check-ignore output/reliability/probe/samples.jsonl
```

预期：测试通过；`git check-ignore` 输出该 probe 路径。

- [ ] **步骤 4：独立提交**

```powershell
git add scripts/r3_model_reliability.py tests/release/test_r3_model_reliability.py .gitignore
git diff --cached --check
git commit -m "feat(可靠性): 写入脱敏批次证据"
```

---

### 任务 3：实现一次性 HTTP/SSE 客户端和 Chat 完整样本

**文件：**
- 修改：`scripts/r3_model_reliability.py`
- 修改：`tests/release/test_r3_model_reliability.py`

- [ ] **步骤 1：写 SSE 成功链和禁止重提红灯**

用 `httpx.MockTransport` 建立固定响应：

```python
import httpx

from scripts.r3_model_reliability import ProductApiClient, run_chat_sample


class R3ChatTests(unittest.TestCase):
    def test_chat_reads_sse_runtime_conversation_and_checkpoint_once(self) -> None:
        calls: list[tuple[str, str]] = []
        run_id = "a" * 32
        conversation_id = "b" * 32
        marker = "R3-CHAT-20260811T010203Z-ab12cd-001"

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.method == "POST" and request.url.path.endswith("/stream/agents/run"):
                body = (
                    f"event: started\ndata: {{\"run_id\":\"{run_id}\","
                    f"\"conversation_id\":\"{conversation_id}\","
                    "\"route\":\"chat_no_tools\"}\n\n"
                    f"event: final\ndata: {{\"kind\":\"final\",\"content\":\"{marker}\"}}\n\n"
                    f"event: done\ndata: {{\"run_id\":\"{run_id}\"}}\n\n"
                    "event: end\ndata: {}\n\n"
                )
                return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
            if request.url.path.endswith(f"/runs/{run_id}"):
                return httpx.Response(200, json={"task": {
                    "task_id": run_id,
                    "status": "succeeded",
                    "input": {"tool_mode": "none", "route": "chat_no_tools"},
                    "result": {"final_answer": marker, "events": []},
                    "error": "",
                }})
            if request.url.path.endswith("/checkpoints"):
                return httpx.Response(200, json={"total": 1, "checkpoints": [{"checkpoint_id": "cp-1"}]})
            if request.url.path.endswith(f"/conversations/{conversation_id}/messages"):
                return httpx.Response(200, json={"messages": [
                    {"role": "user", "content": f"请只回复：{marker}"},
                    {"role": "assistant", "content": marker},
                ]})
            raise AssertionError(str(request.url))

        spec = build_sample_plan("20260811T010203Z-ab12cd")[0]
        api = ProductApiClient(
            "http://xagent.test/api/v1",
            token="memory-only-token",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        result = run_chat_sample(api, spec, model="qwen3:4b")
        self.assertTrue(result.success)
        self.assertTrue(result.exact_match)
        self.assertEqual(result.checkpoint_id, "cp-1")
        self.assertEqual(result.tool_call_count, 0)
        self.assertEqual(
            calls.count(("POST", "/api/v1/stream/agents/run")),
            1,
        )
        with self.assertRaises(RuntimeError):
            run_chat_sample(api, spec, model="qwen3:4b")
```

预期红灯：缺少客户端和 Chat 执行器。

- [ ] **步骤 2：实现最小 API 客户端和 SSE 解析**

实现：

```python
FORBIDDEN_ROUTE_PATTERNS = (
    "/creative",
    "/canvas",
    "/editor",
    "/media/generate",
    "/media/tasks",
    "/produce",
)


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

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if any(pattern in path for pattern in FORBIDDEN_ROUTE_PATTERNS):
            self.forbidden_route_detected = True
        return self.client.request(
            method,
            f"{self.base_url}{path}",
            headers={**self._headers(), **kwargs.pop("headers", {})},
            **kwargs,
        )

    def claim_submission(self, sample_id: str, path: str) -> None:
        key = (sample_id, path)
        if key in self.business_submissions:
            raise RuntimeError(f"duplicate business submission: {sample_id} {path}")
        self.business_submissions.add(key)


class HarnessError(RuntimeError):
    """测试工具合同、解析或本地执行错误；它会中止批次。"""
```

`parse_sse(response)` 必须逐行读取 `event:` 和 `data:`，每个空行产出一个 `(event_name, json_payload)`；非法 JSON 抛 `HarnessError`，不把它误记为模型失败。

- [ ] **步骤 3：实现 Chat 判定顺序**

`run_chat_sample` 固定执行：

1. `claim_submission(sample_id, "/stream/agents/run")`；
2. POST `{"goal": "请只回复：<marker>", "tool_mode": "none", "capabilities": []}`；
3. 读取 started/run/conversation、final、done、error、tool_call、tool_result；
4. GET `/runs/{run_id}`、`/checkpoints?run_id={run_id}`、`/stream/conversations/{conversation_id}/messages`；
5. 精确比较 SSE final、`task.result.final_answer` 和最后一条 assistant message；
6. `finish_reason` 只读取公开字段，否则 `unknown`。

判定优先级固定为：HTTP 非 2xx → `http_error`；超时 → `timeout`；产品失败且 error 含 `model_empty_response_after_retry` → `model_empty_response`；成功但任一 final 不精确或出现工具事件 → `false_success`；成功但 run/conversation 缺失 → `missing_persistence`；成功但 checkpoint 缺失 → `missing_checkpoint`；全部满足才成功。失败时只有 `terminal_status != succeeded`、error 非空、无 done 且无 final 才记 `fail_closed=True`。

- [ ] **步骤 4：补失败链敏感性测试并转绿**

增加两个 fake SSE 用例：

- `error(model_empty_response_after_retry) → end` 且 DB task failed：结果 `success=False`、`error_code=model_empty_response`、`fail_closed=True`；
- SSE/DB 都 `succeeded` 但 final 为 `WRONG`：结果 `false_success=True`、`error_code=false_success`、批次硬失败。

运行：

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q -k "Chat or PlanAndSummary or EvidenceWriter"
```

预期：全部通过；fake transport 中 Chat POST 精确一次。

- [ ] **步骤 5：独立提交**

```powershell
git add scripts/r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --cached --check
git commit -m "feat(可靠性): 验证真实 Chat 样本链"
```

---

### 任务 4：实现 Scheduler attempt 1 与强制暂停

**文件：**
- 修改：`scripts/r3_model_reliability.py`
- 修改：`tests/release/test_r3_model_reliability.py`

- [ ] **步骤 1：写 create/run/poll/pause 红灯**

fake transport 必须记录并断言：

```python
class R3SchedulerTests(unittest.TestCase):
    def test_scheduler_runs_attempt_one_once_and_pauses_in_finally(self) -> None:
        # POST /scheduler/jobs -> job_id
        # POST /scheduler/jobs/{job_id}/run -> attempt 1 pending
        # GET  /scheduler/jobs/{job_id}/runs -> attempt 1 succeeded
        # PATCH /scheduler/jobs/{job_id}/toggle -> enabled false
        # 断言 create body: interval_seconds=86400, max_retries=0
        # 断言 result 精确 marker、error 为空、agent_run_id 非空
        # 断言 create/run-now 各一次，toggle 恰一次

    def test_scheduler_failure_is_kept_and_job_is_still_paused(self) -> None:
        # runs 返回 failed/error；结果必须 scheduler_terminal_error、fail_closed=True
        # 即使失败，toggle 仍恰一次；不得第二次 run-now
```

运行并确认因 `run_scheduler_sample` 缺失而红。

- [ ] **步骤 2：实现 Scheduler 单样本**

`run_scheduler_sample(api, spec, model, sleep, monotonic)` 固定行为：

```python
create_payload = {
    "name": f"R3 reliability {spec.batch_id} {spec.index:03d}",
    "goal": f"请只回复：{spec.marker}",
    "role": None,
    "interval_seconds": 86_400,
    "max_retries": 0,
    "retry_backoff_seconds": 60,
}
```

- create 和 run-now 前分别调用 `claim_submission`；
- 每 2 秒 GET runs，只读取 `attempt == 1`，终态集合固定为 `succeeded|failed|interrupted`；
- 600 秒仍非终态记 `timeout`，但不发第二个 run-now；
- `finally` 中 PATCH toggle `enabled=false`，并 GET jobs 确认持久化为 false；
- succeeded + result 不精确或 error 非空 → `false_success`；
- failed/interrupted + error 非空 → `scheduler_terminal_error` 且 `fail_closed=True`；
- 暂停失败覆盖 `cleanup_ok=False`、`error_code=cleanup_failed`，即使答案正确也不算成功；
- `run_id` 使用 `agent_run_id`，`task_id` 使用 Scheduler run `run_id`，`job_id` 使用创建返回值。

- [ ] **步骤 3：转绿并证明没有业务重试**

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q -k Scheduler
```

预期：成功和失败用例都通过；每个 sample 的 create、run-now、toggle 调用次数均精确为 1。

- [ ] **步骤 4：独立提交**

```powershell
git add scripts/r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --cached --check
git commit -m "feat(可靠性): 验证调度样本与暂停清理"
```

---

### 任务 5：实现 file_write 工件、patch 和 reject 清理

**文件：**
- 修改：`scripts/r3_model_reliability.py`
- 修改：`tests/release/test_r3_model_reliability.py`

- [ ] **步骤 1：写完整工件成功链红灯**

fake API 返回 R2 已验证的真实结构：

```python
parallel_body = {
    "run_id": "parent-run",
    "status": "succeeded",
    "sub_results": [{
        "run_id": "parent-run_sub0",
        "status": "succeeded",
        "steps": 2,
        "error": "",
        "isolated": True,
        "diff_stat": " R3_RELIABILITY_x_001.md | 1 +",
        "diff": "+R3-FILE-WRITE-x-001",
        "development_task_id": "d" * 32,
        "development_task_status": "awaiting_review",
    }],
}
```

测试还要提供：

- GET detail：`awaiting_review`、非空 `result_commit`、目标文件位于 `diff_stat`；
- GET patch：同时包含文件名和 marker；
- fake shell：worktree 存在、commit 可解析、reject 后 worktree/branch 不存在；
- POST reject：body 精确 `{"confirm_task_id": task_id}`，返回 `rejected`。

断言：parallel-run 和 reject 各一次；`patch_sha256` 等于本地计算；结果成功、artifact_count 至少 4。

- [ ] **步骤 2：实现容器内只读工件检查器**

定义 `ShellRunner = Callable[[Sequence[str]], CompletedProcess[str]]` 并注入测试。正式命令只允许：

```text
docker compose --env-file <env> -f <compose> -p <project> exec -T api \
  test -d /data/.xagent-worktrees/<task_id>
docker compose --env-file <env> -f <compose> -p <project> exec -T api \
  git -C /data/.xagent-worktrees/<task_id> cat-file -e <result_commit>^{commit}
docker compose --env-file <env> -f <compose> -p <project> exec -T api \
  git -C /data/workspace branch --list agent/<task_id>
```

`task_id` 必须先通过 `^[a-f0-9]{32}$`，`result_commit` 必须通过 `^[a-f0-9]{40}$`；不得把任意 API 文本插入 shell 字符串。命令使用参数数组，不使用 `shell=True`。

- [ ] **步骤 3：实现单次 parallel-run 和 finally reject**

POST body 固定为：

```python
payload = {
    "tasks": [{
        "goal": (
            f"必须调用 file_write 工具在当前工作区创建 {spec.filename}，"
            f"文件内容必须精确为 {spec.marker}（允许末尾换行），不得只用文字回答。"
        ),
        "capabilities": ["file_write"],
    }],
    "coordinator_goal": f"R3 可靠性样本 {spec.sample_id}",
    "use_worktrees": True,
}
```

成功条件全部满足后才 `success=True`：sub succeeded、isolated、development status awaiting_review、detail result_commit、worktree、commit、diff、patch、文件名、marker 和 SHA-256。任一 succeeded 但工件缺失 → `false_success`；产品失败且 detail 为 failed/timeout/cancelled、error 非空且无可读 patch → 对应真实失败并 `fail_closed=True`。

只要 development task 到达 awaiting_review，就在 `finally` POST `/development-tasks/{id}/reject`，随后 GET detail 确认 rejected，并用只读 shell 确认 worktree 和 `agent/{id}` 分支消失。patch 可以保留，因为当前 rejected 状态允许审计读取。

- [ ] **步骤 4：补 patch mismatch 和 reject failure 红灯后转绿**

分别让 fake patch 缺 marker、fake reject 返回 409，断言错误码为 `patch_mismatch`、`cleanup_failed`，两个样本都不能成功，也不能触发第二次 parallel-run。

运行：

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q -k FileWrite
```

- [ ] **步骤 5：独立提交**

```powershell
git add scripts/r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --cached --check
git commit -m "feat(可靠性): 验证 file_write 工件与清理"
```

---

### 任务 6：实现无副作用预检、模型事实和日志审计

**文件：**
- 修改：`scripts/r3_model_reliability.py`
- 修改：`tests/release/test_r3_model_reliability.py`

- [ ] **步骤 1：写预检红灯**

测试用 fake shell 锁定以下失败均发生在 `BatchRecorder.start()` 前：

- Git 工作树非 clean；
- `api/worker/web/postgres/redis/qdrant/platform-mcp/prometheus/grafana` 任一非 running/healthy；
- `aicg-minio` 或 `aicg-postgres` 不存在、非 healthy，或运行前后 ID 变化；
- deep health 的 database/redis/qdrant 任一非 healthy；
- Worker pong 不是有效节点；
- API 或 Worker 的 effective model 不是 `ollama/qwen3:4b` 或配置模型不是 `qwen3:4b`；
- Celery active/reserved/scheduled 非空，避免与正式 50 样本争用。

预期：`run_preflight` 不存在导致红灯。

- [ ] **步骤 2：实现固定只读命令和 `PreflightSnapshot`**

预检命令参数必须由 CLI 的 compose/env/project 组成，禁止 `down`、`up`、`restart`、`rm`、`prune`、`pause` 和 `unpause`。模型读取使用容器内只读 Python：

```text
docker compose ... exec -T api python -c "from xagent.adapters.llm import get_llm_client; print(get_llm_client().effective_model)"
docker compose ... exec -T worker python -c "from xagent.adapters.llm import get_llm_client; print(get_llm_client().effective_model)"
```

只接受 `ollama/qwen3:4b` 或工具调用路径可能返回的 `ollama_chat/qwen3:4b`，汇总公开模型统一记为 `qwen3:4b`；proxy URL、API key 或 secret 不进入输出。

`run_preflight` 在 API 注册之前完成 Git、Docker、health 和任务空闲检查；预检失败返回结构化 code 并退出 2，不创建 batch 目录、不注册用户、不调用模型。

- [ ] **步骤 3：写日志计数红灯并实现**

`audit_logs(text)` 只返回计数：

```python
def audit_logs(text: str) -> LogsAudit:
    return LogsAudit(
        mock_hits=text.count("MockLLM"),
        forbidden_route_hits=sum(text.count(item) for item in FORBIDDEN_ROUTE_PATTERNS),
        traceback_hits=text.count("Traceback (most recent call last)"),
        qwen_route_hits=text.count("qwen3:4b"),
    )
```

正式工具使用 batch start UTC 调用 `docker compose logs --since <utc> api worker`；只写上述数字，不保存完整日志。`MockLLM > 0` 或 forbidden route > 0 是硬失败；Traceback 记录但不自动等同产品失败，必须与 sample/error 对照写入报告。

- [ ] **步骤 4：运行预检/日志测试并独立提交**

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q -k "Preflight or Logs"
git add scripts/r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --cached --check
git commit -m "feat(可靠性): 增加批次预检与日志审计"
```

---

### 任务 7：实现不可变批次、第二租户探针和 CLI 退出码

**文件：**
- 修改：`scripts/r3_model_reliability.py`
- 创建：`scripts/run_r3_model_reliability.py`
- 修改：`tests/release/test_r3_model_reliability.py`

- [ ] **步骤 1：写严格串行和不重试红灯**

构造 fake executor，在第 3 个 sample 返回真实产品失败。断言：

- 仍按固定顺序执行完 50 个 sample；
- 每个 `sample_id` 只出现一次；
- 失败样本保留在分母中，不补发第 51 个样本；
- Scheduler 和 file_write cleanup 已由各执行器完成；
- 结果为 passed 或 failed，不能因产品失败误标 aborted。

再让第 3 个 executor 抛 `KeyboardInterrupt`，断言只落 2 行 JSONL，summary 为 aborted，后续 executor 不执行，已有目录不能续跑。

- [ ] **步骤 2：写第二租户隔离探针红灯**

实现测试 fake API：第二 tenant token 对第一 tenant 的三个路径分别返回 404、403、404：

```text
GET /runs/<first-chat-run-id>
GET /checkpoints/<first-chat-checkpoint-id>
GET /development-tasks/<first-file-write-task-id>
```

断言 `isolation_ok=True`。任一路径返回 200 必须返回 `tenant_isolation_breach`，批次硬失败。缺少任一锚点时探针不允许跳过，返回 `harness_error` 并使批次失败。

- [ ] **步骤 3：实现注册、批次 ID 和编排**

`generate_batch_id()` 固定格式：

```python
def generate_batch_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{secrets.token_hex(3)}"
```

预检通过后：

1. 在内存生成 44 字符随机密码；
2. POST `/auth/register` 创建 `username=r3-reliability-<batch>`、`tenant_id=r3-reliability-<batch>`；
3. token 只赋给 `ProductApiClient.token`，不写 logger/JSON/异常；
4. `BatchRecorder.start()` 后才开始 sample 1；
5. 顺序遍历固定 plan，执行器返回后立即 append/flush；
6. 50 个样本后注册第二 tenant 并运行隔离探针；
7. 收集 since-start 日志，构建 summary，写 summary/logs/report；
8. `finally` 再次读取服务和受保护容器 ID；身份漂移把批次标 failed，不能修改容器状态。

只有 `KeyboardInterrupt`、`SystemExit`、解析器错误或未建模的工具异常进入 aborted；HTTP 错误、产品超时、模型空响应、错误终态和缺工件都生成普通失败 `SampleResult` 并继续剩余样本。

- [ ] **步骤 4：实现薄 CLI 与固定退出码**

`scripts/run_r3_model_reliability.py` 只包含：

```python
from __future__ import annotations

from r3_model_reliability import cli


if __name__ == "__main__":
    raise SystemExit(cli())
```

`cli()` 参数固定为：

```text
--api-base-url   默认 http://127.0.0.1:18000/api/v1
--health-url     默认 http://127.0.0.1:18000/health/deep
--compose-file   默认 deploy/compose/docker-compose.yml
--env-file       默认 deploy/compose/r2.env.local
--project-name   默认 xagent-r2
--output-root    默认 output/reliability
--report-path    默认 docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md
--preflight-only 只执行无副作用预检，不创建 batch、用户或模型请求
```

CLI 不接受 password、token、Authorization、model override、sample count、retry count、并发数或 batch ID。测试分别 fake passed/failed/aborted/preflight，断言退出 0/1/2/2；另断言 `--preflight-only` 不调用注册、recorder 或任一样本执行器。stdout 只包含 batch_id、status 和公开文件路径。

- [ ] **步骤 5：运行全 R3 合同并独立提交**

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q
git add scripts/r3_model_reliability.py scripts/run_r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --cached --check
git commit -m "feat(可靠性): 编排不可变 R3 基线批次"
```

---

### 任务 8：完成离线回归、静态审计和执行前冲突门

**文件：**
- 不新增产品文件；只修复由任务 1–7 自己引入的问题。

- [ ] **步骤 1：运行 R3 与 R2 release contracts**

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q
& apps/api/.venv/Scripts/python.exe -m unittest discover -s tests/release -p "test_r2_*.py" -v
```

预期：全部通过；若 R2 失败，先判断是否由 R3 文件或 `.gitignore` 引起，禁止修改无关产品实现来追绿。

- [ ] **步骤 2：运行当前 Web/API 后端发布范围**

```powershell
& apps/api/.venv/Scripts/python.exe scripts/run_webapi_release_tests.py
```

预期：通过既有显式排除边界；记录精确 passed/skipped/warnings，不用历史数字代替。

- [ ] **步骤 3：运行静态与安全门**

```powershell
& apps/api/.venv/Scripts/ruff.exe check scripts/r3_model_reliability.py scripts/run_r3_model_reliability.py tests/release/test_r3_model_reliability.py
& apps/api/.venv/Scripts/ruff.exe format --check scripts/r3_model_reliability.py scripts/run_r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --check
rg -n "Bearer |Authorization:|access_token|password=|BEGIN .*PRIVATE KEY|reasoning_content|system_prompt" scripts/r3_model_reliability.py scripts/run_r3_model_reliability.py tests/release/test_r3_model_reliability.py
Test-Path apps/api/uv.lock
git status --short --branch
```

预期：Ruff、format、diff 通过；secret scan 只能命中测试中的公开占位并逐条解释；`apps/api/uv.lock` 为 false；除当前任务文件外无改动。

- [ ] **步骤 4：执行同工作区冲突和运行任务只读检查**

在正式 batch 前记录：

- `git status` clean、无 `.git/index.lock` 和其他 Git lock；
- 无其他进程在同 checkout 执行 build/test/write；
- Celery active/reserved/scheduled 均为空；
- `/api/v1/development-tasks?status=running` 为空；
- 当前核心/扩展/保护容器 ID、镜像、health；
- 不执行 build、up、restart、down、pause、prune 或 volume 操作。

若同 checkout 存在写任务或业务 run，停止并协调；不得用正式 50 样本与其竞争。

- [ ] **步骤 5：把 R3-A 从 Ready 转为工具已就绪的 CLAIMED**

仅当任务 1–8 全绿时，把任务 0 的条目从 `Ready` 移到 `In Progress` 并更新为：

```markdown
- [R3-A] 真实 Ollama 可靠性基线 | 状态：CLAIMED | 证据：固定 30/10/10 合同、不可变批次、脱敏输出、SLO 判定和现有 R2 回归已通过；正式 50 样本尚未开始。
```

提交：

```powershell
git add docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git diff --cached --check
git commit -m "docs(任务板): 标记 R3 基线工具就绪"
```

---

### 任务 9：运行唯一正式 50 样本不可变批次

**文件：**
- 生成但不提交：`output/reliability/<batch_id>/samples.jsonl`
- 生成但不提交：`output/reliability/<batch_id>/summary.json`
- 生成但不提交：`output/reliability/<batch_id>/logs-audit.json`
- 生成并待审：`docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md`

- [ ] **步骤 1：运行工具自身 preflight-only 路径**

调用任务 7 已由测试锁定的 `--preflight-only`；该模式只执行任务 6 的只读预检并退出，不生成 batch、不注册用户、不调用模型。

运行：

```powershell
& apps/api/.venv/Scripts/python.exe scripts/run_r3_model_reliability.py --preflight-only
```

预期：exit 0，输出 `preflight=passed`；服务、模型、任务空闲、保护容器和 Git 全部通过。

- [ ] **步骤 2：最后确认正式执行边界**

记录当前 HEAD、branch、clean status、预检时间、核心/扩展/保护容器 ID。确认没有第二个 benchmark 进程：

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_r3_model_reliability.py*' } | Select-Object ProcessId,CommandLine
```

预期：正式启动前只有当前只读检查进程或没有匹配项。

- [ ] **步骤 3：只运行一次正式批次**

```powershell
& apps/api/.venv/Scripts/python.exe scripts/run_r3_model_reliability.py
```

约束：

- 不添加 `try-again`、不手工补跑单个 marker、不改样本数量；
- 允许 GET 轮询、patch 下载和 cleanup；
- 产品失败继续记录，harness crash/人工中止标 aborted 后立即停止；
- 运行期间不改代码、不切模型、不重启服务、不并行压测；
- commentary 最多报告可执行阶段进度，不把未完成结果称为通过。

- [ ] **步骤 4：按批次终态停在正确门**

- `passed`：继续任务 10，任务板可转 `REVIEW`；
- `failed`：不重跑，继续任务 10，任务板转 `PARTIAL` 并记录失败分布；
- `aborted`：不续写、不拼接，任务板转 `BLOCKED`，保留原始目录；只有修复 harness 并重新得到 Owner 指令后才允许新批次。

---

### 任务 10：交叉审计原始结果、报告和任务板

**文件：**
- 修改：`docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md`
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`

- [ ] **步骤 1：机械核对 JSONL 与 summary 一致性**

使用短只读 Python 命令核对：

- JSONL 恰有 50 行且 sample_id 唯一；aborted 时行数与 completed_samples 精确相等；
- 30/10/10 数量、成功数、失败码分布和 P95 可由 JSONL 重算得到；
- summary 的 hard failures 与 raw flags 一致；
- logs-audit 的 MockLLM/forbidden 数与报告一致；
- 每个 Scheduler job 都 `enabled=false`；
- 每个 awaiting_review file_write 都已 reject，worktree/branch 已清；
- 第二 tenant 三项读取均 403/404；
- raw 文件 SHA-256 写入报告，但 raw 正文不提交。

- [ ] **步骤 2：人工复核失败与假成功语义**

逐个非成功样本确认：

- 产品状态、error、SSE done/final、DB task、Scheduler run 或 development task 是否一致；
- `succeeded + wrong final/artifact` 必须是 false_success，不能降级为普通 wrong_final；
- `model_empty_response_after_retry` 不能被写成“模型回答成功”；
- `finish_reason=unknown` 保持 unknown；
- cleanup failure 不被成功率掩盖。

- [ ] **步骤 3：完成脱敏报告**

报告固定包含：

1. HEAD、worktree、Compose project、本机/单实例边界；
2. 批次 ID、UTC 起止、模型、50 样本矩阵；
3. 三类成功率、P50/P95/max 和门槛；
4. 每种失败码数量、false success 和 fail-closed 覆盖；
5. Scheduler pause、file_write reject、tenant isolation、MockLLM/forbidden 证据；
6. raw 文件路径和 SHA-256；
7. 未验证的短剧、桌面、多机、付费 provider、远程发布；
8. 最终结论只能是 `passed`、`failed` 或 `aborted`，不得升级为企业级全面完成。

- [ ] **步骤 4：按真实结果更新任务板**

- passed：把 In Progress 中的 R3-A 状态从 `CLAIMED` 更新为 `REVIEW`；
- failed：把状态从 `CLAIMED` 更新为 `PARTIAL`，列出不达标的成功率、P95 或硬失败；
- aborted：把状态从 `CLAIMED` 更新为 `BLOCKED`，列出中断样本和 harness 原因；
- 不写 `DONE`，独立复审与 Owner 决策仍未完成。

- [ ] **步骤 5：最终验证并提交证据**

```powershell
& apps/api/.venv/Scripts/python.exe -m pytest tests/release/test_r3_model_reliability.py -q
& apps/api/.venv/Scripts/python.exe -m unittest discover -s tests/release -p "test_r2_*.py" -v
& apps/api/.venv/Scripts/ruff.exe check scripts/r3_model_reliability.py scripts/run_r3_model_reliability.py tests/release/test_r3_model_reliability.py
& apps/api/.venv/Scripts/ruff.exe format --check scripts/r3_model_reliability.py scripts/run_r3_model_reliability.py tests/release/test_r3_model_reliability.py
git diff --check
git check-ignore output/reliability/<batch_id>/samples.jsonl
git status --short --branch
```

只暂存脱敏报告和任务板；原始 output 不得进入 index：

```powershell
git add docs/coordination/reports/WEB_API_R3_MODEL_RELIABILITY_BASELINE.md docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git diff --cached --name-only
git diff --cached --check
git commit -m "docs(证据): 记录 R3 模型可靠性基线"
git status --short --branch
```

预期：提交恰含报告和任务板；工作树 clean；未 push、未 tag、未发布。

---

## 最终验收清单

- [ ] 计划、工具、测试和报告均位于实际 worktree `D:\AI编程库\项目库\进行中的项目\xiong bao\xagent\.worktrees\webapi-release-hardening`。
- [ ] 正式批次只有一个 `batch_id`，没有补样、拼接、替换或并发执行。
- [ ] Chat/Scheduler/file_write 数量严格为 30/10/10。
- [ ] 三类成功率、P95、假成功、fail-closed、MockLLM、forbidden 和 tenant isolation 均由 raw 重算。
- [ ] 每个 Scheduler 已暂停，每个成功 file_write 已 reject 并清理 worktree/branch。
- [ ] JSONL/summary/logs/report 不含密码、token、Authorization、reasoning 或 system prompt。
- [ ] R2 release contracts 和 Web/API backend release scope 新鲜通过。
- [ ] 未修改生产 API/schema/model route，未下载模型、未调用付费 provider。
- [ ] 未执行 Docker 重建、重启、down、volume 删除或其他项目容器操作。
- [ ] 任务板状态与真实 batch status 一致，未提前写 DONE。
- [ ] 最终提交不包含 `output/reliability/`，且未 push/tag/release。
