import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  createWorkspace,
  renameWorkspace,
  sortWorkspaces,
  createCustomAgentProfile,
} from "../src/shell/workspaceModels.ts";
import {
  createDefaultSnapshot,
  hydrateWorkspaceState,
  readPersistedShellSnapshot,
  writePersistedShellSnapshot,
} from "../src/shell/workspaceStorage.ts";

function makeSurface(overrides = {}) {
  return {
    taskId: "chat",
    kind: "chat",
    route: "/chat",
    title: "对话",
    subtitle: "统一工作区中的主对话上下文",
    badge: "工作区",
    pinned: true,
    isPrimary: true,
    status: "ready",
    ...overrides,
  };
}

async function read(relativePath) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("createWorkspace uses Chinese fallback names for task, project, and agent", () => {
  assert.equal(createWorkspace({ id: "task-1", kind: "task", name: "   " }).name, "未命名任务");
  assert.equal(createWorkspace({ id: "project-1", kind: "project" }).name, "未命名项目");
  assert.equal(createWorkspace({ id: "agent-1", kind: "agent", name: "" }).name, "未命名智能体");
});

test("renameWorkspace keeps the old name when the next name is empty", () => {
  const workspace = createWorkspace({ id: "project-1", kind: "project", name: "品牌升级" });

  const renamed = renameWorkspace(workspace, "   ");

  assert.equal(renamed.name, "品牌升级");
});

test("sortWorkspaces keeps pinned records ahead of newer unpinned ones", () => {
  const pinned = createWorkspace({
    id: "pinned",
    kind: "task",
    name: "置顶任务",
    pinned: true,
    timestamp: 100,
  });
  const unpinned = createWorkspace({
    id: "unpinned",
    kind: "task",
    name: "普通任务",
    pinned: false,
    timestamp: 999,
  });

  const sorted = sortWorkspaces([unpinned, pinned]);

  assert.deepEqual(
    sorted.map((workspace) => workspace.id),
    ["pinned", "unpinned"],
  );
});

test("hydrateWorkspaceState falls back to defaults when JSON is malformed", () => {
  const primarySurfaces = [makeSurface()];
  const fallback = createDefaultSnapshot(primarySurfaces);

  const hydrated = hydrateWorkspaceState("{not-json", primarySurfaces);

  assert.deepEqual(hydrated, fallback);
});

test("createCustomAgentProfile preserves the provided baseRole and name", () => {
  const profile = createCustomAgentProfile({
    id: "agent-reviewer",
    name: "审阅助手",
    persona: {
      baseRole: "reviewer",
      tone: "direct",
    },
    description: "负责审阅输出",
    timestamp: 42,
  });

  assert.equal(profile.name, "审阅助手");
  assert.equal(profile.persona.baseRole, "reviewer");
});

test("hydrateWorkspaceState merges missing primary surfaces into a non-empty snapshot", () => {
  const primarySurfaces = [
    makeSurface({ taskId: "chat", title: "对话", route: "/chat" }),
    makeSurface({ taskId: "workflows", kind: "workflow", title: "工作流", route: "/workflows" }),
  ];
  const persisted = JSON.stringify({
    workspaces: [
      {
        id: "primary:chat",
        kind: "task",
        name: "对话",
        description: "统一工作区中的主对话上下文",
        pinned: true,
        updatedAt: 100,
        surface: {
          taskId: "chat",
          taskKind: "chat",
          route: "/chat",
          title: "对话",
          subtitle: "统一工作区中的主对话上下文",
          status: "ready",
          pinned: true,
          isPrimary: true,
        },
      },
    ],
    customAgents: [],
    userDock: { name: "当前用户", title: "本地工作台", description: "说明", avatarSeed: "dock" },
  });

  const hydrated = hydrateWorkspaceState(persisted, primarySurfaces);

  assert.deepEqual(
    [...hydrated.workspaces.map((workspace) => workspace.id)].sort(),
    ["primary:chat", "primary:workflows"],
  );
});

test("workspace snapshot round-trip preserves createdAt and stable ordering after rename", () => {
  const primarySurfaces = [];
  const alpha = createWorkspace({
    id: "alpha",
    kind: "project",
    name: "Alpha",
    pinned: false,
    timestamp: 100,
  });
  const beta = createWorkspace({
    id: "beta",
    kind: "project",
    name: "Beta",
    pinned: true,
    timestamp: 50,
  });
  const renamedAlpha = renameWorkspace(alpha, "Alpha Prime", 300);

  const storage = new Map();
  globalThis.localStorage = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      storage.set(key, String(value));
    },
    removeItem(key) {
      storage.delete(key);
    },
    clear() {
      storage.clear();
    },
    key(index) {
      return [...storage.keys()][index] ?? null;
    },
    get length() {
      return storage.size;
    },
  };

  writePersistedShellSnapshot({
    workspaces: sortWorkspaces([renamedAlpha, beta]),
    customAgents: [],
    userDock: { name: "当前用户", title: "本地工作台", description: "说明", avatarSeed: "dock" },
  });

  const hydrated = readPersistedShellSnapshot(primarySurfaces);

  assert.equal(hydrated.workspaces.find((workspace) => workspace.id === "alpha")?.createdAt, 100);
  assert.equal(hydrated.workspaces.find((workspace) => workspace.id === "alpha")?.updatedAt, 300);
  assert.deepEqual(
    hydrated.workspaces.map((workspace) => workspace.id),
    ["beta", "alpha"],
  );
});

test("frontend preview boundary copy explains demo-only behavior across auxiliary pages", async () => {
  const [
    agentsSource,
    memorySource,
    openSourceSource,
    settingsLayoutSource,
    shellContextPanelSource,
  ] = await Promise.all([
    read("../src/pages/AgentsPage.tsx"),
    read("../src/pages/MemoryPage.tsx"),
    read("../src/pages/OpenSourcePage.tsx"),
    read("../src/components/settings/SettingsLayout.tsx"),
    read("../src/components/layout/ShellContextPanel.tsx"),
  ]);

  assert.match(
    agentsSource,
    /预览态：当前‘角色调度’优先生成任务拆解建议，不直接触发真实智能体执行。/,
  );
  assert.match(
    agentsSource,
    /后端角色接口暂不可用，当前展示的是本地演示角色，仅用于 UI 预览，不代表真实可调度角色集合。/,
  );
  assert.match(
    agentsSource,
    /真实执行时的角色集合、能力边界与可用性以后端返回为准。/,
  );

  assert.match(
    memorySource,
    /辅助模式：当前入口主要用于整理检索意图与跳转索引配置，不直接展示真实知识库命中结果。/,
  );
  assert.match(
    memorySource,
    /真实结果仍需进入索引库或后端检索链路查看。/,
  );

  assert.match(
    openSourceSource,
    /预览态：当前入口优先整理开源比选目标与接入策略，不直接返回实时仓库搜索结果。/,
  );
  assert.match(
    openSourceSource,
    /真实候选仓库仍需进入开源发现链路进一步检索。/,
  );

  assert.match(
    settingsLayoutSource,
    /辅助模式：配置助手当前只生成检查清单与调整建议，不会直接修改本地或远端配置。/,
  );
  assert.match(
    settingsLayoutSource,
    /不会直接写入本地文件、环境变量或远端配置。/,
  );

  assert.match(
    shellContextPanelSource,
    /辅助模式：当前为上下文助手，优先提供总结、建议与跳转，不直接执行后台任务。/,
  );
  assert.match(
    shellContextPanelSource,
    /必要时再引导进入真实执行页面。/,
  );
});

test("frontend execution boundary copy explains preview-vs-run behavior on target pages", async () => {
  const [runConsoleSource, workflowsSource, creativeStudioSource] = await Promise.all([
    read("../src/components/runs/RunConsole.tsx"),
    read("../src/pages/WorkflowsPage.tsx"),
    read("../src/pages/CreativeStudioPage.tsx"),
  ]);

  assert.match(
    runConsoleSource,
    /当前分析助手优先基于已加载的运行详情做本地总结，帮助快速查看 Timeline、Evidence 和 Artifacts。/,
  );
  assert.match(
    runConsoleSource,
    /请基于当前已加载的运行详情回答，优先总结 Timeline、Evidence 与 Artifacts 中已经出现的信息。/,
  );

  assert.match(
    workflowsSource,
    /预览态：这里会先生成页面内步骤草案；正式执行仍以“创建并执行”按钮触发的后端工作流为准。/,
  );
  assert.match(
    workflowsSource,
    /先在页面内生成步骤草案，确认后再通过“创建并执行”提交后端工作流。/,
  );

  assert.match(
    creativeStudioSource,
    /当前输入会优先生成创作草案与页面节点意图；正式生产链路仍以明确的执行按钮和后端返回结果为准。/,
  );
  assert.match(
    creativeStudioSource,
    /“创建画布”用于生成草案；“执行 \/ 生产”才会进入真实后端链路。/,
  );
});


