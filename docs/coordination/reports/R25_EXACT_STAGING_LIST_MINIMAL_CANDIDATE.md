# R25 Exact Staging List For Minimal Send-Review Candidate

> 日期：2026-07-07
> Owner：Claude Code
> 范围：给出当前“最小可送审候选”的**精确暂存文件列表**。
> 边界：本文件只列出建议暂存范围，不实际执行 `git add`。

---

## 1. 使用方法

R25 是给“真正冻结前的手工或半自动暂存”使用的。

建议执行顺序：

1. 先确认 R24 的默认拍板建议仍成立；
2. 再按本文件的 **A / B 两组** 去暂存；
3. 暂存后检查 staged file list；
4. 若无误，再形成候选 commit。

---

## 2. A 组：代码 / 测试 / 运行配置

### 根目录与 CI
- `.github/workflows/ci.yml`
- `README.md`

### 后端源码
- `apps/api/xagent/api/v1/agents.py`
- `apps/api/xagent/api/v1/canvas.py`
- `apps/api/xagent/api/v1/creative_studio.py`
- `apps/api/xagent/api/v1/workflows.py`
- `apps/api/xagent/core/orchestration/loop.py`
- `apps/api/xagent/core/runtime/service.py`
- `apps/api/xagent/enterprise/auth/users.py`
- `apps/api/xagent/infra/repos/workflow.py`
- `apps/api/xagent/infra/settings.py`

### 后端测试
- `apps/api/tests/test_creative_studio.py`
- `apps/api/tests/test_orchestration.py`
- `apps/api/tests/test_runtime_runs.py`
- `apps/api/tests/test_settings.py`
- `apps/api/tests/test_workflow.py`

### 前端源码
- `apps/web/src/App.tsx`
- `apps/web/src/index.css`
- `apps/web/src/api/runtime.ts`
- `apps/web/src/api/chatStream.ts`
- `apps/web/src/components/chat/ConversationalCommand.tsx`
- `apps/web/src/components/effects/AmbientAurora.tsx`
- `apps/web/src/components/layout/AppShell.tsx`
- `apps/web/src/components/layout/CollapsedRail.tsx`
- `apps/web/src/components/layout/TopBar.tsx`
- `apps/web/src/components/layout/WorkspaceSidebar.tsx`
- `apps/web/src/components/layout/ShellContextPanel.tsx`
- `apps/web/src/components/runs/RunConsole.tsx`
- `apps/web/src/components/runs/RunValidationPanel.tsx`
- `apps/web/src/components/settings/GeneralSettings.tsx`
- `apps/web/src/components/settings/SettingsLayout.tsx`
- `apps/web/src/pages/AgentsPage.tsx`
- `apps/web/src/pages/ChatPage.tsx`
- `apps/web/src/pages/CreativeStudioPage.tsx`
- `apps/web/src/pages/EditorPage.tsx`
- `apps/web/src/pages/LoginPage.tsx`
- `apps/web/src/pages/MemoryPage.tsx`
- `apps/web/src/pages/OpenSourcePage.tsx`
- `apps/web/src/pages/ProfessionalModePage.tsx`
- `apps/web/src/pages/RunPage.tsx`
- `apps/web/src/pages/WorkflowsPage.tsx`
- `apps/web/src/shell/shellRoutes.ts`
- `apps/web/src/shell/useShellStore.tsx`
- `apps/web/src/shell/workspaceStorage.ts`

### 前端测试
- `apps/web/tests/runConsoleViews.test.mjs`
- `apps/web/tests/runtimeApi.test.mjs`
- `apps/web/tests/workspaceCatalog.test.mjs`
- `apps/web/tests/chatStream.test.mjs`

### 前端静态资源
- `apps/web/public/assets/xiongbao-logo.png`
- `apps/web/public/assets/xiongbao-mascot.png`

### E2E
- `tests/e2e/specs/creative-smoke.spec.ts`
- `tests/e2e/specs/full-flow.spec.ts`

### 运行 / 部署配置
- `deploy/compose/.env.example`
- `deploy/compose/docker-compose.yml`
- `deploy/helm/templates/worker-web.yaml`

---

## 3. B 组：最小 release/readiness 文档主干

### 核心发布与状态文档
- `docs/COMMERCIAL_STATUS_SOURCE_OF_TRUTH.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST_V1.md`
- `docs/ENVIRONMENT_BASELINE_V1.md`
- `docs/RELEASE_RUNBOOK_V1.md`
- `docs/RELEASE_MESSAGE_CONSISTENCY_AUDIT_R8.md`
- `docs/ROADMAP.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/INTEGRATION_GUIDE.md`
- `docs/项目总览与开发指南.md`
- `docs/XIONG_BAO_接手与启动说明_2026-07-03.md`

### 当前候选与交付主索引
- `docs/coordination/TASK_BOARD.md`
- `docs/coordination/reports/delivery-report.md`
- `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
- `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
- `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`
- `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`
- `docs/coordination/reports/R23_MINIMAL_SEND_REVIEW_CANDIDATE_FILESET.md`
- `docs/coordination/reports/R24_CANDIDATE_FREEZE_EXECUTION_SHEET.md`

---

## 4. 本轮不要暂存的文件

### 明确不要进候选
- `apps/api/api-8000.err.log`
- `apps/api/api-8000.log`
- `apps/api/r3-api-8000.err.log`
- `apps/api/r3-api-8000.log`
- `apps/api/r3-canvas-snapshot.json`
- `apps/web/frontend-3000-20260702-201604.err.log`
- `apps/web/frontend-3000-20260702-201604.log`
- `apps/web/frontend-3000-20260703-123118.err.log`
- `apps/web/frontend-3000-20260703-123118.log`
- `apps/web/r3-web-3100.err.log`
- `apps/web/r3-web-3100.log`
- `apps/web/08_diff_fix/codex-ui-1to1-audit-20260705.md`
- `docs/FRONTEND_未提交改动收口清单_2026-07-03.md`
- `docs/FRONTEND_演示态标识方案_2026-07-03.md`
- `docs/FRONTEND_演示态标识逐文件改动清单_2026-07-03.md`
- `docs/FRONTEND_页面验收执行版_2026-07-03.md`
- `docs/coordination/EXECUTION_LIVE_OUTPUT_PROTOCOL.md`
- `docs/coordination/README.md`
- `docs/coordination/TASK_PACKAGE_PROTOCOL.md`
- `docs/superpowers/plans/2026-07-01-unified-runtime-phase2-a.md`
- `docs/superpowers/plans/2026-07-03-frontend-preview-boundaries.md`
- `docs/superpowers/plans/2026-07-05-commercial-readiness-execution-plan.md`

### 本轮先不纳入，待拍板
- `deploy/helm/templates/deployment.yaml`
- `deploy/helm/values.yaml`
- `deploy/keycloak/xagent-realm.json`
- `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
- `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`
- `docs/coordination/reports/evidence/r9-key-pages/01-login.png`
- `docs/coordination/reports/evidence/r9-key-pages/02-chat-workbench.png`
- `docs/coordination/reports/evidence/r9-key-pages/03-workflow.png`
- `docs/coordination/reports/evidence/r9-key-pages/04-run-console.png`
- `docs/coordination/reports/evidence/r9-key-pages/05-settings-index.png`
- `tests/e2e/specs/r9-visual-evidence.spec.ts`

---

## 5. 暂存后必须检查的 4 件事

在真正形成候选 commit 前，必须检查：

1. staged 文件列表里**没有** `.log`、snapshot、audit 记录；
2. staged 文件列表里**没有** Helm / Keycloak / 扩展证据包（除非已拍板同意）；
3. staged 文件列表里**包含** A 组与 B 组的核心文件；
4. staged diff 对应的验证口径仍然成立：
   - 前端 `lint/typecheck/build` 通过
   - 后端 `ruff/pytest` 通过
   - 许可证门禁通过

---

## 6. 一句话结论

> 如果现在就要开始真正冻结，这份 R25 就是“默认应暂存哪些文件”的精确清单；先按它形成 staged candidate，再决定拍板项，最后才进入 branch / commit / CI 绑定。
