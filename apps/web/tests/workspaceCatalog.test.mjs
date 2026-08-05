import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { URL } from "node:url";
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

async function read(relativePath) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

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

test("formal entry removes anonymous fallback and demo workflow seeds", async () => {
  const [clientSource, loginSource, shellStoreSource, generalSettingsSource, storageSource, e2eSource] = await Promise.all([
    read("../src/api/client.ts"),
    read("../src/pages/LoginPage.tsx"),
    read("../src/shell/useShellStore.tsx"),
    read("../src/components/settings/GeneralSettings.tsx"),
    read("../src/shell/workspaceStorage.ts"),
    read("../../../tests/e2e/specs/full-flow.spec.ts"),
  ]);

  assert.doesNotMatch(clientSource, /ANONYMOUS_KEY/);
  assert.doesNotMatch(clientSource, /setAnonymousSession/);
  assert.doesNotMatch(clientSource, /isAnonymousSession/);
  assert.match(clientSource, /export function isLoggedIn\(\): boolean \{\s*return !!getToken\(\);\s*\}/s);

  assert.doesNotMatch(loginSource, /匿名进入工作区/);
  assert.doesNotMatch(loginSource, /admin\/admin/);
  assert.doesNotMatch(loginSource, /先匿名进入工作区/);

  assert.doesNotMatch(shellStoreSource, /name:\s*"demo"/);
  assert.doesNotMatch(shellStoreSource, /goal:\s*index === 0 \? "你好" : ""/);
  assert.doesNotMatch(shellStoreSource, /本地会话状态正在驱动工作台/);

  assert.doesNotMatch(generalSettingsSource, /lite 模式可留空/);
  assert.doesNotMatch(storageSource, /本地工作台/);
  assert.doesNotMatch(e2eSource, /匿名登录页/);
});
