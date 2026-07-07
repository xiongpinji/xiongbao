# R22 Candidate Inclusion List

> 日期：2026-07-07
> Owner：Claude Code
> 范围：基于当前工作树状态，为下一版候选提供可执行的“纳入 / 排除 / 待拍板”清单。
> 用途：用于冻结候选范围，不等于已经冻结候选。

---

## 1. 使用方式

冻结候选时，按以下顺序使用本清单：

1. 先处理 **Include**：这些默认应进入候选。
2. 再确认 **Exclude**：这些默认不应进入候选。
3. 最后由负责人拍板 **Needs decision**：这些文件不是垃圾，但是否进入候选会影响 CI、部署姿态、审查范围或交付材料边界。

---

## 2. Include（建议直接纳入候选）

## 2.1 后端源码与测试

### API / runtime / infra / auth 源码
- `apps/api/xagent/api/v1/agents.py`
- `apps/api/xagent/api/v1/canvas.py`
- `apps/api/xagent/api/v1/creative_studio.py`
- `apps/api/xagent/api/v1/workflows.py`
- `apps/api/xagent/core/orchestration/loop.py`
- `apps/api/xagent/core/runtime/service.py`
- `apps/api/xagent/enterprise/auth/users.py`
- `apps/api/xagent/infra/repos/workflow.py`
- `apps/api/xagent/infra/settings.py`

**理由：** 当前运行时、creative/workflow 主链、full-mode 安全/配置边界、统一 runtime 详情读取都在这些文件内，属于下一版候选的真实产品代码。

### 后端测试
- `apps/api/tests/test_creative_studio.py`
- `apps/api/tests/test_orchestration.py`
- `apps/api/tests/test_runtime_runs.py`
- `apps/api/tests/test_settings.py`
- `apps/api/tests/test_workflow.py`

**理由：** 这些测试与当前源码主链配套，且已用于本轮本地最终验证；其中 creative/workflow 的 `delivery.failure` 契约已经同步复绿。

---

## 2.2 前端源码、静态资源与测试

### 前端主源码
- `apps/web/src/App.tsx`
- `apps/web/src/index.css`
- `apps/web/src/api/runtime.ts`
- `apps/web/src/api/chatStream.ts`
- `apps/web/src/components/layout/AppShell.tsx`
- `apps/web/src/components/layout/CollapsedRail.tsx`
- `apps/web/src/components/layout/TopBar.tsx`
- `apps/web/src/components/layout/WorkspaceSidebar.tsx`
- `apps/web/src/components/layout/ShellContextPanel.tsx`
- `apps/web/src/components/runs/RunConsole.tsx`
- `apps/web/src/components/runs/RunValidationPanel.tsx`
- `apps/web/src/components/settings/GeneralSettings.tsx`
- `apps/web/src/components/settings/SettingsLayout.tsx`
- `apps/web/src/components/chat/ConversationalCommand.tsx`
- `apps/web/src/components/effects/AmbientAurora.tsx`
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

**理由：** 这些都是当前 Web 工作台的真实应用代码，不是 demo、草稿或构建产物。

### 前端静态资源
- `apps/web/public/assets/xiongbao-logo.png`
- `apps/web/public/assets/xiongbao-mascot.png`

**理由：** 两张图片被源码直接引用，属于真实运行所需资产，而不是截图或临时图片。

### 前端测试
- `apps/web/tests/runConsoleViews.test.mjs`
- `apps/web/tests/runtimeApi.test.mjs`
- `apps/web/tests/workspaceCatalog.test.mjs`
- `apps/web/tests/chatStream.test.mjs`

**理由：** 当前新增/修改源码已有对应测试支撑，应与源码一起冻结。

---

## 2.3 E2E 测试

- `tests/e2e/specs/creative-smoke.spec.ts`
- `tests/e2e/specs/full-flow.spec.ts`

**理由：** 这两组是当前关键链路 E2E 的主验证文件，也是 release/readiness 口径反复引用的运行态证据来源。

---

## 2.4 部署与运行配置（默认纳入）

- `.github/workflows/ci.yml`
- `deploy/compose/.env.example`
- `deploy/compose/docker-compose.yml`
- `deploy/helm/templates/worker-web.yaml`

**理由：** 这些文件已直接影响下一版候选的 CI / compose / worker 启动路径，应与当前代码状态一起纳入，避免“代码候选”和“验证/部署定义”脱节。

> 注：`ci.yml` 也在“Needs decision”里补充说明，因为它虽然建议纳入，但会影响远端 CI 执行面，负责人仍应明确确认。

---

## 2.5 核心发布文档（建议纳入候选文档集）

- `README.md`
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
- `docs/coordination/TASK_BOARD.md`
- `docs/coordination/reports/delivery-report.md`
- `docs/coordination/reports/R18_CANDIDATE_FRESHNESS_AUDIT.md`
- `docs/coordination/reports/R20_FINAL_WRAP_UP_DELIVERY.md`
- `docs/coordination/reports/R21_CANDIDATE_FREEZE_R4_R5_CLOSURE_CHECKLIST.md`

**理由：** 这些文件承载当前唯一事实源、发布门禁、运行手册、候选新鲜度、最终收尾结论与闭环路径，是形成“可送审候选”的最小文档集合。

---

## 3. Exclude（建议明确排除）

## 3.1 日志文件

### API 日志
- `apps/api/api-8000.err.log`
- `apps/api/api-8000.log`
- `apps/api/r3-api-8000.err.log`
- `apps/api/r3-api-8000.log`

### Web 日志
- `apps/web/frontend-3000-20260702-201604.err.log`
- `apps/web/frontend-3000-20260702-201604.log`
- `apps/web/frontend-3000-20260703-123118.err.log`
- `apps/web/frontend-3000-20260703-123118.log`
- `apps/web/r3-web-3100.err.log`
- `apps/web/r3-web-3100.log`

**理由：** 这些是本地运行输出，不属于源码、测试、配置或正式文档。

---

## 3.2 运行期快照与一次性审计材料

- `apps/api/r3-canvas-snapshot.json`
- `apps/web/08_diff_fix/codex-ui-1to1-audit-20260705.md`

**理由：** 前者是运行期状态快照，后者是一次性 UI 审计记录，都不应作为下一版候选组成部分。

---

## 3.3 过程性 / 中间态文档

### FRONTEND_ 系列
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

**理由：** 这些文件属于过程性执行材料、阶段性策划或多代理协作协议，不是下一版候选的稳定交付文档。

---

## 4. Needs decision（需要负责人拍板）

## 4.1 CI / 部署姿态相关

### `.github/workflows/ci.yml`
- 默认建议：**纳入**
- 需要拍板原因：会直接改变远端 CI 结构与执行成本；若下一版候选要绑定新的远端 CI，这个文件最好一起冻结。

### Helm 主模板
- `deploy/helm/templates/deployment.yaml`
- `deploy/helm/values.yaml`

- 默认建议：**待拍板**
- 原因：它们是真部署配置，但当前是否达到“应作为正式候选部署定义”的程度，需要结合实际 Helm 目标决定。

### Keycloak realm
- `deploy/keycloak/xagent-realm.json`

- 默认建议：**待拍板**
- 原因：这是合法配置，但带明显环境假设；要确认是否将其作为下一版候选身份配置一起冻结。

---

## 4.2 审查输入 / 证据型文档

### 关键 coordination 报告
- `docs/coordination/reports/R16_FULL_MODE_REHEARSAL_PREP.md`
- `docs/coordination/reports/R17_PR_EVIDENCE_MATRIX_SOURCE.md`
- `docs/coordination/reports/R19_FULL_MODE_SECRET_HANDOFF_TEMPLATE.md`
- `docs/coordination/reports/R9_KEY_PAGE_VISUAL_EVIDENCE.md`

### R9 截图证据目录
- `docs/coordination/reports/evidence/r9-key-pages/01-login.png`
- `docs/coordination/reports/evidence/r9-key-pages/02-chat-workbench.png`
- `docs/coordination/reports/evidence/r9-key-pages/03-workflow.png`
- `docs/coordination/reports/evidence/r9-key-pages/04-run-console.png`
- `docs/coordination/reports/evidence/r9-key-pages/05-settings-index.png`

### 视觉证据 E2E
- `tests/e2e/specs/r9-visual-evidence.spec.ts`

- 默认建议：**待拍板**
- 原因：
  - 如果下一版候选希望包含完整内部 release dossier / reviewer evidence pack，这些应纳入；
  - 如果只冻结“最小可送审代码候选”，这些可以不作为主候选一部分，只通过 `delivery-report.md` 做索引引用。

---

## 5. 建议的冻结方案

## 5.1 方案 A：最小可送审候选（推荐）

纳入：
- 所有真实源码 / 测试 / 静态资源
- 关键 CI 与 compose 配置
- 核心 release/readiness 文档
- R18 / R20 / R21 / TASK_BOARD / delivery-report

排除：
- 日志
- snapshot
- 一次性审计笔记
- FRONTEND_* 过程文档
- superpowers/plans
- coordination 协议文档

待拍板：
- CI 是否与候选一起冻结
- Helm / Keycloak 是否进入本次候选
- R16/R17/R19/R9 是否进入完整内部送审档案

## 5.2 方案 B：完整内部 release dossier

在方案 A 基础上，再纳入：
- R16
- R17
- R19
- R9 视觉证据与截图
- `tests/e2e/specs/r9-visual-evidence.spec.ts`

适用场景：
- 需要把“代码候选 + 审查输入 + 验收证据”一次性打包给内部 reviewer / 发布负责人。

---

## 6. 最小执行建议

如果马上开始冻结候选，建议按这个顺序：

1. 先把 **Exclude** 全部排掉；
2. 再按 **方案 A** 形成最小候选；
3. 对 **Needs decision** 逐项拍板；
4. 拍板完成后，固定 branch / commit，生成真正 frozen candidate；
5. 以该候选重新绑定远端 CI，再进入 R4 / R5。

---

## 7. 一句话结论

> 当前工作树已经可以整理出“最小可送审候选”，但在真正冻结前，仍需先排除日志/快照/过程材料，并对 CI、Helm/Keycloak、以及证据型文档是否随候选打包做一次明确拍板。
