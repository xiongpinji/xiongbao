import test from "node:test";
import assert from "node:assert/strict";
import {
  createWorkspace,
  renameWorkspace,
  sortWorkspaces,
  createCustomAgentProfile,
} from "../src/shell/workspaceModels.ts";
import { createDefaultSnapshot, hydrateWorkspaceState } from "../src/shell/workspaceStorage.ts";

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
