import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function read(relativePath) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("shellRoutes defines encoded run route helpers for the unified console", async () => {
  const source = await read("../src/shell/shellRoutes.ts");

  assert.match(source, /export type ShellTaskKind = .*"run"/);
  assert.match(source, /const RUN_ROUTE_PATTERN/);
  assert.match(source, /export function isRunRoute\(route: string\)/);
  assert.match(source, /RUN_ROUTE_PATTERN\.test\(route\)/);
  assert.match(source, /export function createRunShellRoute\(/);
  assert.match(source, /const encodedRunId = encodeURIComponent\(runId\)/);
  assert.match(source, /taskId: `run:\$\{runId\}`/);
  assert.match(source, /route: `\/runs\/\$\{encodedRunId\}`/);
  assert.match(source, /badge: "运行"/);
});

test("shell runtime provider and store expose active run-surface wiring", async () => {
  const [mainSource, storeSource] = await Promise.all([
    read("../src/main.tsx"),
    read("../src/shell/useShellStore.tsx"),
  ]);

  assert.match(mainSource, /ShellStoreProvider/);
  assert.match(mainSource, /<ShellStoreProvider>/);
  assert.match(storeSource, /syncRunTask:\s*\(\s*runId: string/);
  assert.match(storeSource, /createRunShellRoute\(runId, options\)/);
  assert.match(storeSource, /kind: snapshot\.kind/);
});

test("chat and workflow pages sync the shell run surface before navigating", async () => {
  const [chatSource, workflowSource] = await Promise.all([
    read("../src/pages/ChatPage.tsx"),
    read("../src/pages/WorkflowsPage.tsx"),
  ]);

  assert.match(chatSource, /useShellActions/);
  assert.match(chatSource, /const \{ syncRunTask \} = useShellActions\(\);/);
  assert.match(chatSource, /syncRunTask\(data\.run_id, \{ source: "chat" \}\);/);
  assert.match(chatSource, /navigate\(`\/runs\/\$\{encodeURIComponent\(data\.run_id\)\}`\)/);
  assert.match(chatSource, /syncRunTask\(nextRun\.run_id, \{ source: "chat" \}\);/);
  assert.match(chatSource, /navigate\(`\/runs\/\$\{encodeURIComponent\(nextRun\.run_id\)\}`\)/);

  assert.match(workflowSource, /useShellActions/);
  assert.match(workflowSource, /const \{ syncRunTask \} = useShellActions\(\);/);
  assert.match(workflowSource, /syncRunTask\(nextView\.run_id, \{ source: "workflow" \}\);/);
  assert.match(workflowSource, /navigate\(`\/runs\/\$\{encodeURIComponent\(nextView\.run_id\)\}`\)/);
});

test("creative page uses runtime run id compatibility and syncs shell before navigation", async () => {
  const [creativeSource, apiSource, backendSource] = await Promise.all([
    read("../src/pages/CreativeStudioPage.tsx"),
    read("../src/api/index.ts"),
    read("../../api/xagent/api/v1/creative_studio.py"),
  ]);

  assert.match(apiSource, /interface ProductionResult/);
  assert.match(apiSource, /run_id\?: string;/);
  assert.match(apiSource, /task_id\?: string;/);

  assert.match(creativeSource, /useShellActions/);
  assert.match(creativeSource, /const \{ syncRunTask \} = useShellActions\(\);/);
  assert.match(creativeSource, /const runId = result\.run_id \?\? result\.task_id \?\? result\.storyboard_id;/);
  assert.match(creativeSource, /syncRunTask\(runId, \{ source: "creative" \}\);/);
  assert.match(creativeSource, /navigate\(`\/runs\/\$\{encodeURIComponent\(runId\)\}`\)/);
  assert.match(creativeSource, /syncRunTask\(result\.workflow\.run_id, \{ source: "creative" \}\);/);
  assert.match(creativeSource, /navigate\(`\/runs\/\$\{encodeURIComponent\(result\.workflow\.run_id\)\}`\)/);

  assert.match(backendSource, /runtime_task = _build_creative_task_view\(/);
  assert.match(backendSource, /task_id=result\.storyboard_id/);
  assert.match(backendSource, /_production_runtime_runs\[result\.storyboard_id\] = \{/);
  assert.match(backendSource, /"run_id": result\.storyboard_id/);
});

test("run console exposes validation risk and recovery panel contracts", async () => {
  const [pageSource, consoleSource, panelSource, runtimeSource] = await Promise.all([
    read("../src/pages/RunPage.tsx"),
    read("../src/components/runs/RunConsole.tsx"),
    read("../src/components/runs/RunValidationPanel.tsx"),
    read("../src/api/runtime.ts"),
  ]);

  assert.match(pageSource, /RunConsole/);
  assert.match(consoleSource, /import RunValidationPanel from "\.\/RunValidationPanel\.tsx";/);
  assert.match(consoleSource, /<RunValidationPanel detail=\{detail\} \/>/);

  assert.match(panelSource, /验证 · 风险 · 恢复/);
  assert.match(panelSource, /function pointerLabel\(/);
  assert.match(panelSource, /function renderPointerCard\(/);
  assert.match(panelSource, /function readRisks\(/);
  assert.match(panelSource, /detail\.delivery\.risks/);
  assert.match(panelSource, /detail\.validation\.risks/);
  assert.doesNotMatch(panelSource, /detail\.delivery\.workflow/);
  assert.match(panelSource, /Delivery Risks/);
  assert.match(panelSource, /Validation Risks/);
  assert.match(panelSource, /detail\.delivery\.replay/);
  assert.match(panelSource, /detail\.delivery\.resume/);
  assert.match(panelSource, /detail\.workflow\?\.steps/);
  assert.match(panelSource, /step\.has_approval/);

  assert.match(runtimeSource, /risks\?: string\[];/);
  assert.match(runtimeSource, /replay\?: Record<string, unknown> \| null;/);
  assert.match(runtimeSource, /resume\?: Record<string, unknown> \| null;/);
});
