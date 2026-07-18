# X-Agent 商用成熟度三阶段推进 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 `xagent` 从当前准商用 / 试点可交付状态，按 Phase 1 → Phase 2 → Phase 3 串行推进到正式商用与企业级长期运营。

**架构：** 采用三阶段串行推进。Phase 1 先补齐“内部试点可稳定使用”的功能链路、稳定性、权限/审计与试点交付材料；Phase 2 收口正式商用 GA 所需的版本冻结、目标环境演练、回滚、签字与发布材料；Phase 3 再做企业级长期运营所需的 HA、可观测、治理、容量与保留策略。每个阶段都必须单独通过自己的验收门后再进入下一阶段。

**技术栈：** Markdown、GitHub Actions、FastAPI、React/Vite、Docker Compose、Helm、pytest、Playwright、Locust、Prometheus/Grafana、Langfuse、Postgres、Redis、Qdrant

---

## 文件结构与职责边界

### 新增文件

- `docs/superpowers/plans/2026-07-19-xagent-commercialization-ladder-execution-plan.md`
  - 商用成熟度三阶段的执行顺序、任务清单、依赖关系、阶段门、验收命令。
- `docs/coordination/reports/commercial-readiness-phase1-gap-analysis.md`
  - Phase 1 当前缺口清单：功能链路、稳定性/恢复、数据/权限/审计、试点交付材料。
- `docs/coordination/reports/commercial-readiness-phase2-gate-checklist.md`
  - Phase 2 正式商用 GA 门禁清单：版本冻结、目标环境演练、发布/回滚、签字、证据。
- `docs/coordination/reports/commercial-readiness-phase3-ops-checklist.md`
  - Phase 3 长期运营门禁清单：HA、可观测、审计保留、容量、恢复演练。

### 修改文件

- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
  - 将“当前真状态”与三阶段推进的映射补充为可执行的阶段门。
- `docs/ROADMAP.md`
  - 明确 Phase 1/2/3 的前后关系，避免与历史阶段混淆。
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
  - 把 Phase 2 的 GA 门禁与现有发布检查表对齐。
- `docs/RELEASE_RUNBOOK_V1.md`
  - 在 Phase 2 中需要补齐的发布/回滚/演练要求处增加引用。
- `docs/ENVIRONMENT_BASELINE_V1.md`
  - 在 Phase 1 与 Phase 2 的环境边界中补充试点/正式环境差异。
- `docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
  - 将 Phase 1 / Phase 2 / Phase 3 的不支持范围显式写出来。
- 可能涉及的产品代码（仅在 Phase 1 实现阶段发生）：
  - `apps/api/xagent/api/v1/spine.py`
  - `apps/api/xagent/core/spine/service.py`
  - `apps/api/xagent/core/spine/session.py`
  - `apps/api/xagent/core/spine/release.py`
  - `apps/api/tests/test_spine_release_flow.py`
  - `apps/web/src/components/spine/GoalBoard.tsx`
  - `apps/web/src/components/spine/ReleasePane.tsx`
  - `apps/web/src/tests/goalBoard.test.tsx`

---

## Phase 1：内部试点可稳定使用

### 任务 1：整理 Phase 1 缺口清单并冻结范围

**文件：**
- 创建：`docs/coordination/reports/commercial-readiness-phase1-gap-analysis.md`
- 修改：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 修改：`docs/ROADMAP.md`

- [ ] **步骤 1：编写 Phase 1 缺口测试（文档级）**

```md
# Phase 1 Gap Analysis

## 功能链路缺口
- 登录 / 核心工作台 / task / run / workflow / 结果查看

## 稳定性 / 恢复缺口
- 失败态可见、可恢复、可重试、可解释

## 数据 / 权限 / 审计缺口
- 租户隔离、权限边界、可追溯记录

## 试点交付缺口
- 部署说明、已知问题、运维/排障最小手册
```

- [ ] **步骤 2：运行文档校验**

运行：`git diff --check -- docs/coordination/reports/commercial-readiness-phase1-gap-analysis.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/ROADMAP.md`
预期：退出码 0

- [ ] **步骤 3：提交文档收口**

```bash
git add docs/coordination/reports/commercial-readiness-phase1-gap-analysis.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/ROADMAP.md
git commit -m "docs(readiness): freeze phase1 gap analysis"
```

### 任务 2：补齐登录 / 核心工作台 / 日常主链的稳定性验收

**文件：**
- 修改：`apps/api/tests/test_spine_api.py`
- 修改：`apps/api/tests/test_spine_session_resume.py`
- 修改：`apps/api/tests/test_spine_release_flow.py`
- 修改：`apps/web/src/tests/goalBoard.test.tsx`
- 视情况修改：`apps/web/src/components/spine/GoalBoard.tsx`
- 视情况修改：`apps/web/src/components/spine/ReleasePane.tsx`

- [ ] **步骤 1：编写失败的 UI/接口回归测试**

```python
async def test_create_goal_requires_spine_execute_permission(client: AsyncClient) -> None:
    token = create_access_token(user_id="viewer-user", tenant_id="tenant-1", roles=["viewer"])

    response = await client.post(
        "/api/v1/spine/goals",
        json={
            "title": "Phase 1",
            "description": "Daily usage path",
        },
        headers=_auth(token),
    )

    assert response.status_code == 403
```

```tsx
it("renders release pane separately from core task columns", () => {
  render(
    <GoalBoard
      snapshot={{
        goal: { title: "Phase 1", phase: "release", status: "active" },
        columns: {
          ready: [{ task_id: "t-1", title: "Build taskboard" }],
          release_ready: [{ task_id: "t-2", title: "Cut candidate" }],
          deploying: [{ task_id: "t-3", title: "Deploy candidate" }],
          recovery: [{ task_id: "t-4", title: "Rollback" }],
        },
        next_action: { kind: "recovery", task_id: "t-4", reason: "verify failed" },
      }}
    />,
  );

  expect(screen.getByText("Release / Recovery")).toBeInTheDocument();
});
```

- [ ] **步骤 2：运行测试验证失败**

运行：
- `cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_api.py -k create_goal_requires_spine_execute_permission -v`
- `cd apps/web && npm test -- goalBoard.test.tsx`

预期：至少一条新测试失败，确认覆盖到了 Phase 1 缺口。

- [ ] **步骤 3：最小实现修复**

```python
# apps/api/xagent/api/v1/spine.py
principal: Principal = Depends(require_permission("spine", "execute"))
```

```tsx
// apps/web/src/components/spine/GoalBoard.tsx
const RELEASE_COLUMNS = ["release_ready", "deploying", "verifying", "delivered", "recovery"] as const;
```

- [ ] **步骤 4：运行测试验证通过**

运行：
- `cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_api.py tests/test_spine_session_resume.py tests/test_spine_release_flow.py -q`
- `cd apps/web && npm test -- goalBoard.test.tsx`

预期：PASS。

- [ ] **步骤 5：提交 Phase 1 日常使用补齐**

```bash
git add apps/api/tests/test_spine_api.py apps/api/tests/test_spine_session_resume.py apps/api/tests/test_spine_release_flow.py apps/api/xagent/api/v1/spine.py apps/web/src/components/spine/GoalBoard.tsx apps/web/src/components/spine/ReleasePane.tsx apps/web/src/tests/goalBoard.test.tsx
git commit -m "feat(readiness): stabilize phase1 daily-use path"
```

### 任务 3：补齐 Phase 1 的稳定性 / 恢复 / 追责门

**文件：**
- 修改：`apps/api/tests/test_worker.py`
- 修改：`apps/api/xagent/api/v1/tasks.py`
- 修改：`apps/api/xagent/api/v1/workflows.py`
- 修改：`apps/api/xagent/core/runtime/service.py`
- 修改：`apps/api/xagent/core/spine/service.py`
- 相关测试：`apps/api/tests/test_worker.py`、`apps/api/tests/test_runtime_runs.py`、`apps/api/tests/test_spine_service.py`

- [ ] **步骤 1：编写失败的恢复/可追责测试**

```python
async def test_task_failure_updates_board_to_recovery(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("xagent.api.v1.tasks.run_agent", AsyncMock(side_effect=RuntimeError("task exploded")))
    ...
    assert terminal["status"] == "failed"
    await _assert_board_task_state(..., expected_status="recovery", ...)
```

```python
def test_summarize_goal_board_rebuilds_from_tasks_when_columns_are_empty() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {},
        "tasks": [
            {"task_id": "t-1", "title": "Blocked task", "status": "blocked", "blocker_reason": "need rollback"},
            {"task_id": "t-2", "title": "Ready task", "status": "ready", "run_id": ""},
        ],
    }

    summary = summarize_goal_board(snapshot)
    assert summary["next_action"] == {"kind": "recovery", "task_id": "t-1", "reason": "need rollback"}
```

- [ ] **步骤 2：运行测试验证失败**

运行：
- `cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_runtime_runs.py tests/test_spine_service.py -q`

预期：至少一项失败（确认恢复链路测试已锁定问题）。

- [ ] **步骤 3：最小实现修复**

```python
# apps/api/xagent/core/spine/service.py
if not _columns_have_tasks(columns):
    if "tasks" in snapshot:
        columns, unknown_status_tasks = _group_tasks_into_columns(snapshot.get("tasks") or [])
```

```python
# apps/api/xagent/api/v1/tasks.py / workflows.py / runtime/service.py
# 保持 update_task_status_by_run_id / load_spine_linkage_by_run_id 路径稳定，错误时明确落 recovery。
```

- [ ] **步骤 4：运行测试验证通过**

运行：
- `cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_runtime_runs.py tests/test_spine_service.py -q`

预期：PASS。

- [ ] **步骤 5：提交 Phase 1 稳定性修复**

```bash
git add apps/api/tests/test_worker.py apps/api/tests/test_runtime_runs.py apps/api/tests/test_spine_service.py apps/api/xagent/api/v1/tasks.py apps/api/xagent/api/v1/workflows.py apps/api/xagent/core/runtime/service.py apps/api/xagent/core/spine/service.py
git commit -m "fix(readiness): harden phase1 recovery path"
```

### 任务 4：补齐 Phase 1 试点交付材料

**文件：**
- 修改：`docs/DELIVERY_MATERIALS_INDEX_V1.md`
- 修改：`docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md`
- 修改：`docs/RELEASE_RUNBOOK_V1.md`
- 修改：`docs/ENVIRONMENT_BASELINE_V1.md`
- 修改：`docs/OPERATIONS_MANUAL_V1.md`

- [ ] **步骤 1：编写试点交付材料回归检查**

```md
## Delivery Materials Check
- admin deployment manual exists
- operations manual exists
- release runbook exists
- known issues / pilot boundaries exist
- support escalation path exists
```

- [ ] **步骤 2：运行文档校验**

运行：`git diff --check -- docs/DELIVERY_MATERIALS_INDEX_V1.md docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md docs/RELEASE_RUNBOOK_V1.md docs/ENVIRONMENT_BASELINE_V1.md docs/OPERATIONS_MANUAL_V1.md`

预期：退出码 0。

- [ ] **步骤 3：提交试点交付材料补齐**

```bash
git add docs/DELIVERY_MATERIALS_INDEX_V1.md docs/KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md docs/RELEASE_RUNBOOK_V1.md docs/ENVIRONMENT_BASELINE_V1.md docs/OPERATIONS_MANUAL_V1.md
git commit -m "docs(readiness): complete phase1 pilot delivery materials"
```

---

## Phase 2：正式商用 GA

### 任务 5：冻结正式商用候选与发布证据入口

**文件：**
- 修改：`docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- 修改：`docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- 修改：`docs/coordination/reports/auto-delivery-phase1-report.md`
- 修改：`docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md`
- 相关发布材料：`docs/RELEASE_RUNBOOK_V1.md`

- [ ] **步骤 1：编写发布冻结回归检查**

```md
## Freeze Checks
- version tagged
- release scope frozen
- remote CI green on candidate
- target environment evidence exists
```

- [ ] **步骤 2：运行文档 / CI 检查**

运行：
- `git diff --check -- docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/coordination/reports/auto-delivery-phase1-report.md docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md`
- `gh pr checks <candidate-pr>`

预期：格式无误，CI 全绿，候选范围固定。

- [ ] **步骤 3：最小实现（若存在发布口径差异）**

```md
# 在 COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md 中追加一节：
## 11. 正式商用 GA 冻结条件
- version frozen
- target env rehearsal done
- rollback proven
- signoff available
```

- [ ] **步骤 4：提交发布证据收口**

```bash
git add docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md docs/coordination/reports/auto-delivery-phase1-report.md docs/coordination/reports/R5_FINAL_REVIEW_PACKAGE.md
git commit -m "docs(readiness): define ga freeze evidence"
```

### 任务 6：正式商用 GA 的目标环境演练与回滚闭环

**文件：**
- 修改：`docs/RELEASE_RUNBOOK_V1.md`
- 修改：`docs/ENVIRONMENT_BASELINE_V1.md`
- 修改：`.github/workflows/ci.yml`
- 测试：`tests/e2e/specs/full-flow.spec.ts`、`apps/api/tests/test_runtime_runs.py`

- [ ] **步骤 1：编写目标环境演练失败测试/清单**

```md
## Rehearsal Checklist
- migrate head
- health/readiness
- login
- task submission
- workflow approval
- rollback
```

- [ ] **步骤 2：运行演练命令**

运行：
- `docker compose --env-file .env config --quiet`
- `docker compose up -d --build`
- `curl -f http://localhost:8000/health`
- `curl -f http://localhost:8000/ready`

预期：全部成功，失败则停止。

- [ ] **步骤 3：将演练结果写入 runbook**

```md
### Rehearsal Evidence
- environment
- timestamp
- logs
- screenshots
- rollback result
```

- [ ] **步骤 4：提交演练闭环**

```bash
git add docs/RELEASE_RUNBOOK_V1.md docs/ENVIRONMENT_BASELINE_V1.md .github/workflows/ci.yml
git commit -m "docs(readiness): close ga rehearsal loop"
```

---

## Phase 3：企业级长期运营

### 任务 7：补齐可观测、告警与容量边界

**文件：**
- 创建：`docs/OPERATIONS_SLO_V1.md`
- 修改：`docs/OPERATIONS_MANUAL_V1.md`
- 修改：`docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- 测试：`tests/load/locustfile.py`（若新增）

- [ ] **步骤 1：写出 SLO / 告警基线测试**

```md
## SLO
- P95 latency
- error rate
- queue backlog
- readiness flaps
```

- [ ] **步骤 2：运行观测验证**

运行：
- `python tests/security/scan.py --host http://localhost:8000`
- `locust -f tests/load/locustfile.py --host http://localhost:8000 --headless -u 50 -r 5 -t 60s`

预期：数据可收集，告警阈值可定义，瓶颈可识别。

- [ ] **步骤 3：将结果写入运维手册**

```md
## Production SLO
- alert thresholds
- oncall owner
- rollback contact
- capacity limits
```

- [ ] **步骤 4：提交企业化治理材料**

```bash
git add docs/OPERATIONS_SLO_V1.md docs/OPERATIONS_MANUAL_V1.md docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md
git commit -m "docs(readiness): add ops and capacity gates"
```

### 任务 8：补齐 HA / K8s / 长期运营验证

**文件：**
- 修改：`deploy/helm/values.yaml`
- 修改：`deploy/helm/templates/*`
- 修改：`deploy/compose/docker-compose.yml`
- 相关验证：`README.md`、`docs/ENVIRONMENT_BASELINE_V1.md`

- [ ] **步骤 1：编写失败的多实例 / secretRef 验证清单**

```md
## HA / K8s Checklist
- multiple replicas
- secretRef or equivalent
- rolling update
- service readiness
- no singleton assumption
```

- [ ] **步骤 2：在等价环境中验证**

运行：
- `helm template ...`
- `kubectl apply --dry-run=client ...`

预期：模板可渲染，secret 不再依赖本地临时值。

- [ ] **步骤 3：提交企业级长期运营收口**

```bash
git add deploy/helm/values.yaml deploy/helm/templates docs/ENVIRONMENT_BASELINE_V1.md README.md
git commit -m "feat(ops): validate long-term enterprise readiness"
```

---

## 验收与最终判定

### 任务顺序要求

- Phase 1 必须先完成并验收；
- Phase 2 只能在 Phase 1 通过后开始；
- Phase 3 只能在 Phase 2 通过后开始。

### 每阶段结束的判定

- **Phase 1 完成**：内部试点可稳定使用，日常主链、恢复、权限 / 审计、试点交付材料齐备；
- **Phase 2 完成**：可正式商用 GA，候选冻结、目标环境演练、签字与发布治理闭环；
- **Phase 3 完成**：企业级长期运营能力（HA、可观测、治理、容量）具备并验证通过。

---

## 规格覆盖度自检

- Phase 1 的功能链路、稳定性 / 恢复、数据 / 权限 / 审计、试点交付材料均有独立任务。
- Phase 2 的候选冻结、发布 / 回滚、目标环境演练、签字与文档闭环均有独立任务。
- Phase 3 的 HA / K8s、可观测、审计保留、容量 / 扩展边界均有独立任务。
- 所有任务均按 2-5 分钟小步骤拆分，具备失败测试、实现、验证、提交的顺序。

---

## 当前结论

这份计划将“商用程度百分百”拆解为可执行的三阶段路径；后续推进时应始终以当前阶段的验收门为准，避免把 Phase 3 的治理能力前置到 Phase 1/2。