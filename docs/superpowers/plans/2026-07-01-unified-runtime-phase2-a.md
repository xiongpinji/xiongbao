# Unified Runtime Phase2-A 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把当前 unified runtime 从“主链可用”升级到“状态单调、失败可追踪、详情精确可读、前端失败态可操作”的 Phase2-A 版本。

**架构：** 本阶段不扩新产品面，只围绕一致性与失败态闭环做加固。后端继续以 `agent_tasks`、`evidence_records`、`workflow_runs` 为事实源：direct/stream 成功与失败主链都做单调状态持久化与失败 bundle；workflow detail 从列表扫描切到单条查询；前端继续复用现有 Run Console，只补失败态卡片与类型约束。所有改动优先复用现有 helper，不引入第二套 runtime persistence 模型。

**技术栈：** FastAPI、SQLAlchemy AsyncSession、Alembic、Celery、React 18、TypeScript、pytest、node:test

---

## 文件结构与职责边界

### 核心修改文件

- `apps/api/xagent/api/v1/agents.py`
  - direct run 成功/失败的统一持久化入口。
- `apps/api/xagent/api/v1/stream.py`
  - stream run 成功/失败的统一持久化入口。
- `apps/api/xagent/api/v1/tasks.py`
  - task 列表/详情对 Celery 非终态的 read-repair 逻辑。
- `apps/api/xagent/worker/celery_app.py`
  - `agent_tasks` 状态机单调化与 read-repair helper。
- `apps/api/xagent/core/runtime/service.py`
  - `/runs/{run_id}` 聚合、workflow 精确读取、失败 bundle 合并。
- `apps/api/xagent/infra/repos/workflow.py`
  - workflow run 单条查询接口。
- `apps/api/tests/test_worker.py`
  - Celery 状态机、read-repair、失败回写测试。
- `apps/api/tests/test_runtime_runs.py`
  - `/runs/{run_id}` success/failure bundle、workflow 精确读取测试。
- `apps/api/tests/test_workflow.py`
  - workflow failed / rolled_back / cancelled bundle 测试。
- `apps/api/tests/test_creative_studio.py`
  - creative partial/failed delivery bundle 测试。
- `apps/web/src/api/runtime.ts`
  - `delivery.failure` 类型收口。
- `apps/web/src/components/runs/RunValidationPanel.tsx`
  - 失败态卡片与推荐动作展示。
- `apps/web/src/components/runs/RunConsole.tsx`
  - 失败态 banner / 顶部摘要增强。
- `apps/web/tests/runtimeApi.test.mjs`
  - `delivery.failure` DTO 测试。
- `apps/web/tests/runConsoleViews.test.mjs`
  - 失败态 UI 接线测试。

### 可选新增文件（仅当现有文件过重时创建）

- `apps/api/xagent/core/runtime/failure_bundle.py`
  - 集中 direct / stream / workflow / creative 的失败 bundle 构造逻辑。
  - 只有当 `runtime/service.py` 或 `creative_studio.py` 变得过重时才创建；默认优先不新增。

---

## 任务 1：direct / stream 成功态原子化、失败态可追踪

**文件：**
- 修改：`apps/api/xagent/api/v1/agents.py`
- 修改：`apps/api/xagent/api/v1/stream.py`
- 修改：`apps/api/xagent/worker/celery_app.py`
- 测试：`apps/api/tests/test_runtime_runs.py`
- 测试：`apps/api/tests/test_worker.py`

- [ ] **步骤 1：补 direct / stream 失败闭环的失败测试**

```python
async def test_runs_api_direct_agent_failure_persists_failed_task_and_failure_bundle(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xagent.api.v1 import agents as agents_api

    async def _boom_run_agent(*args, **kwargs):
        raise RuntimeError("direct run exploded")

    monkeypatch.setattr(agents_api, "run_agent", _boom_run_agent)
    token = create_access_token(user_id="direct-fail", tenant_id="tenant-1", roles=["member"])

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": "direct failure evidence"},
        headers=_auth(token),
    )

    assert resp.status_code == 500
    run_id = resp.json()["run_id"]

    detail = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["task"]["status"] == "failed"
    assert detail.json()["delivery"]["status"] == "blocked"
    assert detail.json()["delivery"]["failure"]["reason"] == "direct run exploded"
    assert [row["kind"] for row in detail.json()["evidence"]] == [
        "request.input",
        "result.failed",
        "delivery.generated",
    ]
```

```python
async def test_runs_api_stream_failure_before_result_still_persists_failed_bundle(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xagent.api.v1 import stream as stream_api

    async def _boom_run_agent(*args, **kwargs):
        raise RuntimeError("stream run exploded")

    monkeypatch.setattr(stream_api, "run_agent", _boom_run_agent)
    token = create_access_token(user_id="stream-fail", tenant_id="tenant-1", roles=["member"])

    resp = await client.post(
        "/api/v1/stream/agents/run",
        json={"goal": "stream failure evidence"},
        headers={**_auth(token), "Accept": "text/event-stream"},
    )

    assert resp.status_code == 200
    assert "event: error" in resp.text
    error_payload = _extract_sse_payload(resp.text, "error")
    run_id = error_payload["run_id"]

    detail = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["task"]["status"] == "failed"
```

- [ ] **步骤 2：运行测试确认当前实现仍有失败态闭环缺口**

运行：

```bash
cd apps/api && pytest tests/test_runtime_runs.py -k "direct_agent_failure or stream_failure_before_result" -q
```

预期：FAIL，表现为 `/runs/{run_id}` 404、evidence 缺失或 failure bundle 字段缺失。

- [ ] **步骤 3：收敛 direct / stream 成功/失败持久化入口**

`apps/api/xagent/worker/celery_app.py`

```python
async def persist_agent_run_bundle_in_session(
    session: AsyncSession,
    *,
    task_id: str,
    run_id: str,
    tenant_id: str,
    owner_id: str,
    kind: str,
    backend: str,
    status: str,
    input_payload: dict[str, Any],
    result_payload: dict[str, Any],
    error: str,
    started_at: datetime | None,
    finished_at: datetime | None,
    validation_summary: dict[str, Any],
    delivery_summary: dict[str, Any],
    preview_summary: dict[str, Any],
    evidence_records: list[dict[str, Any]],
) -> None:
    await persist_agent_task_record_in_session(
        session,
        task_id=task_id,
        run_id=run_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        kind=kind,
        backend=backend,
        status=status,
        input_payload=input_payload,
        result_payload=result_payload,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
        validation_summary=validation_summary,
        delivery_summary=delivery_summary,
        preview_summary=preview_summary,
    )
    await persist_evidence_bundle(
        session,
        tenant_id=tenant_id,
        run_id=run_id,
        task_id=task_id,
        records=evidence_records,
    )
```

`apps/api/xagent/api/v1/agents.py`

```python
run_id = uuid.uuid4().hex
started_at = datetime.now(UTC)
try:
    result = await run_agent(..., run_id=run_id, session=session)
    result_payload = result.to_dict()
    delivery_summary = _build_success_delivery_summary(result_payload)
    await persist_agent_run_bundle_in_session(...)
    await session.commit()
except Exception as exc:
    failed_result = _build_failure_result_summary(run_id=run_id, error=str(exc), role=body.role)
    failed_delivery = _build_failure_delivery_summary(run_id=run_id, result_summary=failed_result)
    await persist_agent_run_bundle_in_session(...)
    await session.commit()
    raise HTTPException(status_code=500, detail={"run_id": run_id, "error": str(exc)})
```

`apps/api/xagent/api/v1/stream.py`

```python
result = None
run_id = uuid.uuid4().hex
started_at = datetime.now(UTC)
...
if result is not None and _is_runtime_persistence_schema_mismatch(exc):
    await queue.put(_sse("done", {"steps": result.steps, "run_id": result.run_id}))
else:
    failed_result = _build_failure_result_summary(...)
    failed_delivery = _build_failure_delivery_summary(...)
    async with get_sessionmaker()() as session:
        await persist_agent_run_bundle_in_session(...)
        await session.commit()
    await queue.put(_sse("error", {"error": failure_error, "run_id": run_id}))
```

- [ ] **步骤 4：运行 direct / stream 相关测试验证通过**

运行：

```bash
cd apps/api && pytest tests/test_runtime_runs.py -k "direct_agent or stream_agent" -q
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add apps/api/xagent/api/v1/agents.py apps/api/xagent/api/v1/stream.py apps/api/xagent/worker/celery_app.py apps/api/tests/test_runtime_runs.py apps/api/tests/test_worker.py
git commit -m "fix: make direct and stream runtime persistence atomic"
```

---

## 任务 2：把 workflow 详情读取从 `limit=200 + scan` 改成精确查询

**文件：**
- 修改：`apps/api/xagent/infra/repos/workflow.py`
- 修改：`apps/api/xagent/core/runtime/service.py`
- 测试：`apps/api/tests/test_runtime_runs.py`

- [ ] **步骤 1：先写精确读取失败测试**

```python
async def test_runs_api_reads_workflow_by_run_id_without_recent_limit(
    client: AsyncClient,
    migrated_db,
) -> None:
    token = create_access_token(user_id="wf-user", tenant_id="tenant-1", roles=["member"])
    async with get_sessionmaker()() as session:
        for index in range(205):
            await persist_workflow_run(
                session,
                {
                    "run_id": f"wf-{index}",
                    "tenant_id": "tenant-1",
                    "spec_name": f"wf-{index}",
                    "status": "completed",
                    "steps": [],
                    "timeline": [],
                },
            )
            await session.commit()

    resp = await client.get("/api/v1/runs/wf-0", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["workflow"]["run_id"] == "wf-0"
```

- [ ] **步骤 2：运行测试确认当前 `limit=200 + scan` 失败**

运行：

```bash
cd apps/api && pytest tests/test_runtime_runs.py -k "without_recent_limit" -q
```

预期：FAIL。

- [ ] **步骤 3：新增 workflow repo 单条读取接口并替换 runtime service**

`apps/api/xagent/infra/repos/workflow.py`

```python
async def load_workflow_run_by_id(
    session: AsyncSession,
    tenant_id: str,
    run_id: str,
) -> dict | None:
    row = await session.get(WorkflowRunORM, run_id)
    if row is None or row.tenant_id != tenant_id:
        return None
    return {
        "run_id": row.run_id,
        "tenant_id": row.tenant_id,
        "spec_name": row.spec_name,
        "status": row.status,
        "steps": json.loads(row.view).get("steps", []) if row.view else [],
        "timeline": json.loads(row.timeline_events) if row.timeline_events else [],
    }
```

`apps/api/xagent/core/runtime/service.py`

```python
async def _load_workflow_view(...):
    return await load_workflow_run_by_id(session, tenant_id, run_id)
```

- [ ] **步骤 4：运行测试验证 workflow 精确读取通过**

运行：

```bash
cd apps/api && pytest tests/test_runtime_runs.py -k "without_recent_limit" -q
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add apps/api/xagent/infra/repos/workflow.py apps/api/xagent/core/runtime/service.py apps/api/tests/test_runtime_runs.py
git commit -m "fix: load workflow runtime detail by run id"
```

---

## 任务 3：补失败态 Delivery Bundle 的结构化字段与前端展示

**文件：**
- 修改：`apps/api/xagent/core/runtime/service.py`
- 修改：`apps/api/xagent/api/v1/workflows.py`
- 修改：`apps/api/xagent/api/v1/creative_studio.py`
- 修改：`apps/web/src/api/runtime.ts`
- 修改：`apps/web/src/components/runs/RunValidationPanel.tsx`
- 修改：`apps/web/src/components/runs/RunConsole.tsx`
- 测试：`apps/api/tests/test_runtime_runs.py`
- 测试：`apps/api/tests/test_creative_studio.py`
- 测试：`apps/web/tests/runtimeApi.test.mjs`
- 测试：`apps/web/tests/runConsoleViews.test.mjs`

- [ ] **步骤 1：先写 workflow / creative failed bundle 测试**

```python
async def test_runs_api_workflow_failed_bundle_has_structured_failure_fields(...) -> None:
    ...
    assert body["delivery"]["failure"] == {
        "state": "failed",
        "source": "workflow",
        "reason": "synthetic workflow failure",
        "step_id": "s1",
        "retryable": False,
        "recommended_action": "检查失败步骤并重新运行",
    }
```

```python
async def test_runs_api_creative_partial_bundle_has_structured_failure_fields(...) -> None:
    ...
    assert body["delivery"]["failure"]["state"] == "blocked"
    assert body["delivery"]["failure"]["source"] == "creative"
    assert body["delivery"]["failure"]["reason"]
```

- [ ] **步骤 2：运行测试确认缺少 `delivery.failure` 而失败**

运行：

```bash
cd apps/api && pytest tests/test_runtime_runs.py tests/test_creative_studio.py -k "structured_failure_fields" -q
```

预期：FAIL。

- [ ] **步骤 3：后端补 `delivery.failure` 字段**

`apps/api/xagent/api/v1/workflows.py`

```python
def _build_workflow_failure_bundle(run_view: dict) -> dict[str, Any] | None:
    status = str(run_view.get("status") or "")
    if status not in {"failed", "rolled_back", "cancelled"}:
        return None
    failed_step = next(
        (step for step in run_view.get("steps") or [] if step.get("status") in {"failed", "rolled_back"}),
        None,
    )
    return {
        "state": "blocked" if status == "rolled_back" else status,
        "source": "workflow",
        "reason": str((failed_step or {}).get("error") or status),
        "step_id": (failed_step or {}).get("id"),
        "step_name": (failed_step or {}).get("name"),
        "retryable": False,
        "recommended_action": "检查失败步骤并重新运行",
    }
```

`apps/api/xagent/api/v1/creative_studio.py`

```python
def _build_production_failure_bundle(result: dict[str, Any]) -> dict[str, Any] | None:
    status = str(result.get("status") or "")
    if status not in {"partial", "failed"}:
        return None
    failed_shot = next(
        (
            shot for shot in result.get("shots") or []
            if shot.get("image_error") or shot.get("video_error")
        ),
        None,
    )
    return {
        "state": "blocked" if status == "partial" else "failed",
        "source": "creative",
        "reason": str((failed_shot or {}).get("video_error") or (failed_shot or {}).get("image_error") or status),
        "step_id": (failed_shot or {}).get("shot_id"),
        "step_name": (failed_shot or {}).get("scene"),
        "retryable": True,
        "recommended_action": "检查失败镜头后重新生成",
    }
```

`apps/api/xagent/core/runtime/service.py`

```python
failure = delivery.get("failure") if isinstance(delivery.get("failure"), dict) else None
if failure is None and workflow_view is not None:
    failure = _build_workflow_failure_bundle(workflow_view)
if failure is None and creative_view is not None:
    failure = deepcopy((creative_view.get("delivery") or {}).get("failure"))
if failure is not None:
    delivery["failure"] = failure
```

- [ ] **步骤 4：前端显示失败态卡片**

`apps/web/src/api/runtime.ts`

```ts
export interface RuntimeFailureSummary {
  state: string;
  source: string;
  reason: string;
  step_id?: string | null;
  step_name?: string | null;
  retryable?: boolean;
  recommended_action?: string | null;
}

export interface RuntimeDeliverySummary extends Record<string, unknown> {
  replay?: Record<string, unknown> | null;
  resume?: Record<string, unknown> | null;
  risks?: string[];
  failure?: RuntimeFailureSummary | null;
}
```

`apps/web/src/components/runs/RunValidationPanel.tsx`

```tsx
function renderFailureCard(failure: RuntimeFailureSummary | null | undefined) {
  if (!failure) return null;
  return (
    <section className="rounded-2xl border border-red-500/20 bg-red-500/5 p-4">
      <div className="text-sm font-medium text-red-200">失败态摘要</div>
      <div className="mt-2 text-sm text-red-100">{failure.reason}</div>
      <div className="mt-2 text-xs text-red-200/80">
        来源：{failure.source} · 状态：{failure.state}
      </div>
      {failure.step_name ? <div className="mt-1 text-xs text-red-200/80">位置：{failure.step_name}</div> : null}
      {failure.recommended_action ? <div className="mt-2 text-xs text-red-100">建议：{failure.recommended_action}</div> : null}
    </section>
  );
}
```

- [ ] **步骤 5：运行后端与前端失败 bundle 测试通过**

运行：

```bash
cd apps/api && pytest tests/test_runtime_runs.py tests/test_creative_studio.py -k "structured_failure_fields" -q
cd ../web && npm run typecheck && node --test tests/runtimeApi.test.mjs tests/runConsoleViews.test.mjs
```

预期：全部 PASS。

- [ ] **步骤 6：Commit**

```bash
git add apps/api/xagent/core/runtime/service.py apps/api/xagent/api/v1/workflows.py apps/api/xagent/api/v1/creative_studio.py apps/web/src/api/runtime.ts apps/web/src/components/runs/RunValidationPanel.tsx apps/web/src/components/runs/RunConsole.tsx apps/api/tests/test_runtime_runs.py apps/api/tests/test_creative_studio.py apps/web/tests/runtimeApi.test.mjs apps/web/tests/runConsoleViews.test.mjs
git commit -m "feat: add structured failure bundles to runtime console"
```

---

## 收口回归

- [ ] **步骤 1：运行后端核心套件**

```bash
cd apps/api && pytest tests/test_worker.py tests/test_runtime_runs.py tests/test_creative_studio.py tests/test_workflow.py tests/test_task_contract.py tests/test_evidence_delivery.py -q
```

- [ ] **步骤 2：运行前端核心套件**

```bash
cd apps/web && npm run typecheck && node --test tests/runtimeApi.test.mjs tests/runConsoleViews.test.mjs
```

- [ ] **步骤 3：记录剩余非阻断项并停手**

```markdown
- workflow detail 当前仍是 limit=200 + scan（可列入 phase2-B）
- direct/stream 的更强事务原子性仍可继续增强
```

---

## 自检

### 规格覆盖度
- direct / stream 原子持久化与失败闭环：任务 1
- workflow 精确读取：任务 2
- workflow / creative 失败 bundle + 前端失败态：任务 3
- 收口回归：最后回归

### 占位符扫描
- 无 TODO / 待定 / 后续实现 占位。

### 类型一致性
- 后端统一使用 `task/run/evidence/delivery/validation/failure`
- 前端统一使用 `RuntimeFailureSummary` 与 `delivery.failure`
- 所有入口继续以 `run_id` 为统一读取主键
