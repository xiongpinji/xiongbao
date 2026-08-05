# R23 Minimal Send-Review Candidate File Set

> 日期：2026-07-07
> Owner：Claude Code
> 范围：给出一份**最小可送审候选文件集**，用于后续真正冻结 branch / commit。
> 边界：本文件只定义建议范围，不执行 `git add`、不创建分支、不替代负责人对 `Needs decision` 项的拍板。

---

## 1. 目的

R22 已经把当前工作树拆成：

- Include
- Exclude
- Needs decision

R23 的目标是在此基础上再向前一步，给出一份：

> **如果现在就要冻结一个“最小可送审候选”，默认建议应纳入哪些文件。**

这份文件集遵循两个原则：

1. **保证代码候选完整可评审**：真实源码、测试、关键静态资源、核心运行/发布配置都在内；
2. **尽量避免把过程性材料、日志、快照、额外证据包一起捆进去**：把候选先收窄，后续需要再加“扩展证据包”。

---

## 2. 推荐冻结方案

### 2.1 默认方案：最小可送审候选

默认建议冻结以下四类：

1. **真实产品代码与测试**
2. **必要静态资源**
3. **关键 CI / compose 配置**
4. **最小 release/readiness 文档集合**

### 2.2 暂不默认纳入

以下内容不进入“最小可送审候选”默认集合：

- 日志
- 运行态快照
- 一次性审计记录
- 过程性 FRONTEND_* 文档
- superpowers/plans
- coordination 协议文档
- 视觉证据与扩展审查输入包
- Helm / Keycloak 等需要单独拍板的部署资产

---

## 3. 最小可送审候选文件集（推荐直接纳入）

## 3.1 根目录与 CI

- `.github/workflows/ci.yml`
- `README.md`

**说明：**
- `ci.yml` 建议随候选一起冻结，因为它直接决定“这版候选对应的远端 CI 是怎么跑的”。
- 这也是本清单里唯一一个“建议纳入但仍需负责人意识到会影响远端 CI 定义”的文件。

---

## 3.2 后端候选文件集

### 源码
- `apps/api/xagent/api/v1/agents.py`
- `apps/api/xagent/api/v1/canvas.py`
- `apps/api/xagent/api/v1/creative_studio.py`
- `apps/api/xagent/api/v1/workflows.py`
- `apps/api/xagent/core/orchestration/loop.py`
- `apps/api/xagent/core/runtime/service.py`
- `apps/api/xagent/enterprise/auth/users.py`
- `apps/api/xagent/infra/repos/workflow.py`
- `apps/api/xagent/infra/settings.py`

### 测试
- `apps/api/tests/test_creative_studio.py`
- `apps/api/tests/test_orchestration.py`
- `apps/api/tests/test_runtime_runs.py`
- `apps/api/tests/test_settings.py`
- `apps/api/tests/test_workflow.py`

**说明：**
- 这是当前 API/runtime/creative/workflow/full-mode 安全与配置边界的主链代码。
- 这些测试已经用于本轮本地最终验证，应与代码一起进入候选。

---

## 3.3 前端候选文件集

### 源码
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

### 测试
- `apps/web/tests/runConsoleViews.test.mjs`
- `apps/web/tests/runtimeApi.test.mjs`
- `apps/web/tests/workspaceCatalog.test.mjs`
- `apps/web/tests/chatStream.test.mjs`

### 静态资源
- `apps/web/public/assets/xiongbao-logo.png`
- `apps/web/public/assets/xiongbao-mascot.png`

**说明：**
- 以上是当前 Web 工作台的真实运行面，不包含日志、不包含构建产物。
- 两张 PNG 是被源码直接依赖的应用资源，应与前端源码一起冻结。

---

## 3.4 E2E 候选文件集

- `tests/e2e/specs/creative-smoke.spec.ts`
- `tests/e2e/specs/full-flow.spec.ts`

**说明：**
- 这两份 E2E 是当前最核心的行为验证文件。
- 它们是“最小可送审候选”中默认保留的 E2E 集合。

---

## 3.5 最小运行 / 发布配置

- `deploy/compose/.env.example`
- `deploy/compose/docker-compose.yml`
- `deploy/helm/templates/worker-web.yaml`

**说明：**
- compose 配置默认应纳入，因为当前 release/rehearsal 路径仍以 compose/full-mode 为主。
- `worker-web.yaml` 属于 worker/web 路径的真实部署模板，保留有助于 reviewer 理解当前 worker 面。

> 注意：`deploy/helm/templates/deployment.yaml`、`deploy/helm/values.yaml`、`deploy/keycloak/xagent-realm.json` 暂不进入最小集合，见第 5 节。

---

## 3.6 最小 release/readiness 文档集合

### 核心状态 / 门禁 / 手册
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

### 当前 release 协调主索引
- `docs/coordination/TASK_BOARD.md`
- `docs/coordination/reports/delivery-report.md`
- `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
- `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
- `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`
- `docs/coordination/reports/R22_CANDIDATE_INCLUSION_LIST.md`

**说明：**
- 这是“最小可送审”所需的文档主干：事实源、门禁、执行手册、候选边界、收尾结论、闭环路径、纳入清单。
- 它们足以支撑 reviewer 理解：当前候选是什么、当前还差什么、哪些事情不能误判为完成。

---

## 4. 明确不进入最小候选的文件

## 4.1 永久排除类

### 日志
- `apps/api/api-8000.err.log`
- `apps/api/api-8000.log`
- `apps/api/r3-api-8000.err.log`
- `apps/api/r3-api-8000.log`
- `apps/web/frontend-3000-20260702-201604.err.log`
- `apps/web/frontend-3000-20260702-201604.log`
- `apps/web/frontend-3000-20260703-123118.err.log`
- `apps/web/frontend-3000-20260703-123118.log`
- `apps/web/r3-web-3100.err.log`
- `apps/web/r3-web-3100.log`

### 运行态快照 / 一次性审计记录
- `apps/api/r3-canvas-snapshot.json`
- `apps/web/08_diff_fix/codex-ui-1to1-audit-20260705.md`

**说明：**
- 这些不应进入任何正式候选。

---

## 4.2 默认不纳入最小候选的过程性文档

### FRONTEND_*
- `docs/FRONTEND_未提交改动收口清单_2026-07-03.md`
- `docs/FRONTEND_演示态标识方案_2026-07-03.md`
- `docs/FRONTEND_演示态标识逐文件改动清单_2026-07-03.md`
- `docs/FRONTEND_页面验收执行版_2026-07-03.md`

### superpowers/plans
- `docs/superpowers/plans/2026-07-01-unified-runtime-phase2-a.md`
- `docs/superpowers/plans/2026-07-03-frontend-preview-boundaries.md`
- `docs/superpowers/plans/2026-07-05-commercial-readiness-execution-plan.md`

### coordination 协议文档
- `docs/coordination/EXECUTION_LIVE_OUTPUT_PROTOCOL.md`
- `docs/coordination/README.md`
- `docs/coordination/TASK_PACKAGE_PROTOCOL.md`

**说明：**
- 这些不是垃圾，但它们更适合作为历史过程材料，不属于“最小可送审候选”。

---

## 5. 拍板项（默认不纳入最小候选，需显式决定）

## 5.1 CI / Helm / Keycloak

### 建议单独拍板
- `deploy/helm/templates/deployment.yaml`
- `deploy/helm/values.yaml`
- `deploy/keycloak/xagent-realm.json`

**默认建议：**
- 暂不放入最小候选。

**原因：**
- 这些是真配置，但是否属于这次候选的正式部署边界，要看你们是否准备把 Helm/K8s 或 Keycloak realm 一并纳入本轮送审范围。

---

## 5.2 扩展审查输入 / 证据包

### 文档
- `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
- `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`

### 视觉证据
- `docs/coordination/reports/evidence/r9-key-pages/01-login.png`
- `docs/coordination/reports/evidence/r9-key-pages/02-chat-workbench.png`
- `docs/coordination/reports/evidence/r9-key-pages/03-workflow.png`
- `docs/coordination/reports/evidence/r9-key-pages/04-run-console.png`
- `docs/coordination/reports/evidence/r9-key-pages/05-settings-index.png`

### 对应测试
- `tests/e2e/specs/r9-visual-evidence.spec.ts`

**默认建议：**
- 不纳入“最小可送审候选”；
- 若要形成“完整内部 release dossier”，再作为扩展包附加纳入。

**原因：**
- 这些内容更偏 reviewer 输入、恢复模板或视觉证据，而不是最小候选的主干。

---

## 6. 真正冻结前的最小执行顺序

### Step 1
先把第 4 节里的内容从候选范围中排除。

### Step 2
按第 3 节形成“最小可送审候选文件集”。

### Step 3
对第 5 节逐项拍板：
- `ci.yml` 是否与本轮候选共同冻结（建议：是）
- Helm / Keycloak 是否进入本轮候选（默认：否）
- R16/R17/R19/R9 是否作为扩展审查包附带（默认：否，除非 reviewer 提前要求）

### Step 4
在拍板完成后：
- 固定 branch
- 固定 commit
- push
- 跑新的远端 CI

> 到这一步，才算真正从“推荐文件集”进入“冻结候选”。

---

## 7. 一句话结论

> 如果现在就要做一个最小可送审候选，默认应冻结：**真实代码 + 测试 + 必要静态资源 + 关键 CI/compose 配置 + 最小 release/readiness 文档主干**；其余证据包、Helm/Keycloak 和过程材料应在负责人拍板后再决定是否追加。
