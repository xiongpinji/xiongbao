import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const creativeStudioPagePath = new URL("../src/pages/CreativeStudioPage.tsx", import.meta.url);
const creativeCanvasStartersPath = new URL("../src/pages/creativeStudio/creativeCanvasStarters.ts", import.meta.url);
const creativeCanvasMappersPath = new URL("../src/pages/creativeStudio/creativeCanvasMappers.ts", import.meta.url);
const creativeMediaTasksPath = new URL("../src/pages/creativeStudio/useCreativeMediaTasks.ts", import.meta.url);
const creativeNodeActionsPath = new URL("../src/pages/creativeStudio/useCreativeNodeActions.ts", import.meta.url);
const creativeEditorBridgePath = new URL("../src/pages/creativeStudio/useCreativeEditorBridge.ts", import.meta.url);

async function importTsModule(url) {
  return import(`${url.href}?t=${Date.now()}`);
}

async function readTextOrNull(url) {
  try {
    return await readFile(url, "utf8");
  } catch {
    return null;
  }
}

test("CreativeStudioPage imports extracted starter and mapper modules", async () => {
  const source = await readTextOrNull(creativeStudioPagePath);

  assert.ok(source, "CreativeStudioPage.tsx should exist");
  assert.match(source, /from\s+"\.\/creativeStudio\/creativeCanvasStarters"/);
  assert.match(source, /from\s+"\.\/creativeStudio\/creativeCanvasMappers"/);
  assert.match(source, /from\s+"\.\/creativeStudio\/useCreativeMediaTasks"/);
  assert.match(source, /from\s+"\.\/creativeStudio\/useCreativeNodeActions"/);
});

test("creativeCanvasStarters exports starter helpers and returns starter graph shapes", async () => {
  const startersModule = await importTsModule(creativeCanvasStartersPath);

  assert.equal(typeof startersModule.starterNodes, "function");
  assert.equal(typeof startersModule.starterEdges, "function");

  const nodes = startersModule.starterNodes();
  const edges = startersModule.starterEdges(nodes);

  assert.ok(Array.isArray(nodes));
  assert.equal(nodes.length, 4);
  assert.ok(nodes.every((node) => node.type === "dramaNode"));
  assert.ok(nodes.every((node) => typeof node.id === "string" && node.id.length > 0));
  assert.ok(nodes.every((node) => typeof node.position?.x === "number" && typeof node.position?.y === "number"));
  assert.ok(nodes.every((node) => typeof node.data?.nodeType === "string"));

  assert.ok(Array.isArray(edges));
  assert.equal(edges.length, 3);
  assert.ok(edges.every((edge) => typeof edge.source === "string" && typeof edge.target === "string"));
  assert.ok(edges.every((edge) => edge.animated === true));
});

test("useCreativeMediaTasks exports the media-task hook and keeps orchestration helpers in the module", async () => {
  const source = await readTextOrNull(creativeMediaTasksPath);

  assert.ok(source, "useCreativeMediaTasks.ts should exist");
  assert.match(source, /\buseCreativeMediaTasks\b/);
  assert.match(source, /\bstartTaskPolling\b/);
  assert.match(source, /\bbatchGenerateMedia\b/);
});

test("useCreativeNodeActions exports the node-actions hook and page wiring keeps the task-3 integration shape", async () => {
  const source = await readTextOrNull(creativeNodeActionsPath);
  const pageSource = await readTextOrNull(creativeStudioPagePath);

  assert.ok(source, "useCreativeNodeActions.ts should exist");
  assert.ok(pageSource, "CreativeStudioPage.tsx should exist");
  assert.match(source, /\buseCreativeNodeActions\b/);
  assert.match(source, /return\s*\{[\s\S]*updateNodeContent[\s\S]*updateNodeSettings[\s\S]*patchNodeData[\s\S]*handleNodeAction[\s\S]*\}/);
  assert.match(pageSource, /from\s+"\.\/creativeStudio\/useCreativeNodeActions"/);
  assert.match(pageSource, /const\s+\{\s*updateNodeContent,\s*updateNodeSettings,\s*patchNodeData,\s*handleNodeAction\s*\}\s*=\s*useCreativeNodeActions\s*\(/);
});

test("CreativeStudioPage imports the extracted editor bridge and the module exports editor bridge helpers", async () => {
  const source = await readTextOrNull(creativeEditorBridgePath);
  const pageSource = await readTextOrNull(creativeStudioPagePath);

  assert.ok(source, "useCreativeEditorBridge.ts should exist");
  assert.ok(pageSource, "CreativeStudioPage.tsx should exist");
  assert.match(pageSource, /from\s+"\.\/creativeStudio\/useCreativeEditorBridge"/);
  assert.match(pageSource, /const\s+\{\s*runEditorForNode,\s*runExportForNode,\s*runAgentClipForNode\s*\}\s*=\s*useCreativeEditorBridge\s*\(/);
  assert.match(source, /export\s+function\s+useCreativeEditorBridge\s*\(/);
  assert.match(source, /\brunEditorForNode\b/);
  assert.match(source, /\brunExportForNode\b/);
  assert.match(source, /\brunAgentClipForNode\b/);
  assert.match(source, /agentClip\(\{\s*instruction\s*(?:,|\})/);
  assert.doesNotMatch(source, /agentClip\(\{\s*prompt\s*(?:,|\})/);
  assert.match(source, /editorTimelineRef\.current\s*=\s*updatedTimeline/);
  assert.match(source, /setEditorTimeline\(updatedTimeline\)/);
});

test("creativeCanvasMappers exports mapper helpers and preserves valid zero positions", async () => {
  const mappersModule = await importTsModule(creativeCanvasMappersPath);

  assert.equal(typeof mappersModule.normalizeNodeType, "function");
  assert.equal(typeof mappersModule.mapCanvasNodeToFlowNode, "function");
  assert.equal(typeof mappersModule.mapDependenciesToEdges, "function");

  const flowNode = mappersModule.mapCanvasNodeToFlowNode({
    node_id: "node-1",
    node_type: "分镜",
    title: "镜头一",
    content: "内容",
    status: "approved",
    agent_note: "agent",
    human_note: "human",
    position: { x: 0, y: 0 },
    dependencies: ["node-0"],
    settings: { prompt: "test" },
    locked: false,
  }, 2, { fallbackPosition: { x: 999, y: 888 } });

  assert.equal(flowNode.id, "node-1");
  assert.equal(flowNode.type, "dramaNode");
  assert.deepEqual(flowNode.position, { x: 0, y: 0 });
  assert.equal(flowNode.data.nodeType, "分镜");
  assert.deepEqual(flowNode.data.dependencies, ["node-0"]);
  assert.equal(flowNode.data.reviewStatus, "approved");
  assert.equal(flowNode.data.executionStatus, "pending");
});

test("normalizeNodeType warns on unknown node types and mapper edge helper builds edges", async () => {
  const mappersModule = await importTsModule(creativeCanvasMappersPath);
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.map(String).join(" "));

  try {
    const normalized = mappersModule.normalizeNodeType("神秘节点");
    assert.equal(typeof normalized, "string");
    assert.ok(normalized.length > 0);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /神秘节点/);
  } finally {
    console.warn = originalWarn;
  }

  const edges = mappersModule.mapDependenciesToEdges([
    {
      node_id: "node-b",
      node_type: "分镜",
      title: "B",
      content: null,
      status: "pending",
      agent_note: "",
      human_note: "",
      position: { x: 10, y: 20 },
      dependencies: ["node-a"],
    },
    {
      node_id: "node-c",
      node_type: "关键帧",
      title: "C",
      content: null,
      status: "pending",
      agent_note: "",
      human_note: "",
      position: { x: 20, y: 40 },
      dependencies: ["node-a", "node-b"],
    },
  ]);

  assert.deepEqual(edges, [
    { id: "e-node-a-node-b", source: "node-a", target: "node-b", animated: true },
    { id: "e-node-a-node-c", source: "node-a", target: "node-c", animated: true },
    { id: "e-node-b-node-c", source: "node-b", target: "node-c", animated: true },
  ]);
});
