import {
  createWorkspace,
  createWorkspaceSurface,
  sortWorkspaces,
  type CustomAgentProfile,
  type WorkspaceRecord,
  type WorkspaceSurface,
} from "./workspaceModels.ts";
import type { ShellRouteSnapshot, ShellTaskKind, ShellTaskStatus } from "./shellRoutes.ts";

export const STORAGE_KEY = "xagent-shell-state";

export interface PersistedUserDockProfile {
  name: string;
  title: string;
  description: string;
  avatarSeed: string;
}

export interface PersistedShellSnapshot {
  workspaces: WorkspaceRecord[];
  customAgents: CustomAgentProfile[];
  userDock: PersistedUserDockProfile;
}

const DEFAULT_USER_DOCK: PersistedUserDockProfile = {
  name: "当前用户",
  title: "工作台",
  description: "管理工作区、智能体与个性化偏好。",
  avatarSeed: "user-dock",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function normalizeUserDock(value: unknown): PersistedUserDockProfile {
  if (!isRecord(value)) {
    return { ...DEFAULT_USER_DOCK };
  }

  return {
    name: typeof value.name === "string" && value.name.trim() ? value.name.trim() : DEFAULT_USER_DOCK.name,
    title: typeof value.title === "string" && value.title.trim() ? value.title.trim() : DEFAULT_USER_DOCK.title,
    description:
      typeof value.description === "string" && value.description.trim()
        ? value.description.trim()
        : DEFAULT_USER_DOCK.description,
    avatarSeed:
      typeof value.avatarSeed === "string" && value.avatarSeed.trim()
        ? value.avatarSeed.trim()
        : DEFAULT_USER_DOCK.avatarSeed,
  };
}

function normalizeWorkspaceSurface(value: Record<string, unknown>, fallbackTaskId: string): WorkspaceSurface {
  return {
    taskId: typeof value.taskId === "string" ? value.taskId : fallbackTaskId,
    taskKind: (typeof value.taskKind === "string" ? value.taskKind : "chat") as ShellTaskKind,
    route: typeof value.route === "string" ? value.route : "/chat",
    title: typeof value.title === "string" ? value.title : "",
    subtitle: typeof value.subtitle === "string" ? value.subtitle : "",
    status: (typeof value.status === "string" ? value.status : "ready") as ShellTaskStatus,
    badge: typeof value.badge === "string" ? value.badge : undefined,
    pinned: Boolean(value.pinned),
    isPrimary: Boolean(value.isPrimary),
  };
}

function mapPrimarySurfaceToWorkspace(surface: ShellRouteSnapshot, index: number): WorkspaceRecord {
  return createWorkspace({
    id: `primary:${surface.taskId}`,
    kind: "task",
    name: surface.title,
    description: surface.subtitle,
    pinned: true,
    surface: createWorkspaceSurface(surface),
    timestamp: Date.now() - index,
  });
}

function mergePrimaryWorkspaces(
  workspaces: WorkspaceRecord[],
  primarySurfaces: ShellRouteSnapshot[],
): WorkspaceRecord[] {
  const existingPrimaryIds = new Set(
    workspaces.filter((workspace) => workspace.surface?.isPrimary).map((workspace) => workspace.id),
  );
  const missingPrimaryWorkspaces = primarySurfaces
    .map(mapPrimarySurfaceToWorkspace)
    .filter((workspace) => !existingPrimaryIds.has(workspace.id));

  return missingPrimaryWorkspaces.length > 0
    ? sortWorkspaces([...workspaces, ...missingPrimaryWorkspaces])
    : sortWorkspaces(workspaces);
}

function normalizeWorkspaces(value: unknown, primarySurfaces: ShellRouteSnapshot[]): WorkspaceRecord[] {
  if (!Array.isArray(value) || value.length === 0) {
    return createDefaultSnapshot(primarySurfaces).workspaces;
  }

  const workspaces = value.flatMap((entry, index) => {
    if (!isRecord(entry)) {
      return [];
    }

    const kind = entry.kind;
    const id = typeof entry.id === "string" ? entry.id : `workspace-${index}`;
    if (kind !== "task" && kind !== "project" && kind !== "agent") {
      return [];
    }

    const surface = isRecord(entry.surface) ? normalizeWorkspaceSurface(entry.surface, id) : null;

    return [
      createWorkspace({
        id,
        kind,
        name: typeof entry.name === "string" ? entry.name : undefined,
        description: typeof entry.description === "string" ? entry.description : undefined,
        pinned: typeof entry.pinned === "boolean" ? entry.pinned : undefined,
        surface,
        createdAt: typeof entry.createdAt === "number" ? entry.createdAt : undefined,
        updatedAt: typeof entry.updatedAt === "number" ? entry.updatedAt : undefined,
      }),
    ];
  });

  return workspaces.length > 0
    ? mergePrimaryWorkspaces(workspaces, primarySurfaces)
    : createDefaultSnapshot(primarySurfaces).workspaces;
}

function normalizeCustomAgents(value: unknown): CustomAgentProfile[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((entry, index) => {
    if (!isRecord(entry) || !isRecord(entry.persona) || typeof entry.persona.baseRole !== "string") {
      return [];
    }

    return [
      {
        id: typeof entry.id === "string" ? entry.id : `custom-agent-${index}`,
        name: typeof entry.name === "string" && entry.name.trim() ? entry.name.trim() : "未命名智能体",
        description: typeof entry.description === "string" ? entry.description.trim() : "",
        persona: {
          baseRole: entry.persona.baseRole,
          tone: typeof entry.persona.tone === "string" ? entry.persona.tone : undefined,
          prompt: typeof entry.persona.prompt === "string" ? entry.persona.prompt : undefined,
          greeting: typeof entry.persona.greeting === "string" ? entry.persona.greeting : undefined,
          tags: Array.isArray(entry.persona.tags)
            ? entry.persona.tags.filter((tag): tag is string => typeof tag === "string")
            : undefined,
        },
        createdAt: typeof entry.createdAt === "number" ? entry.createdAt : Date.now(),
        updatedAt: typeof entry.updatedAt === "number" ? entry.updatedAt : Date.now(),
      },
    ];
  });
}

export function createDefaultSnapshot(primarySurfaces: ShellRouteSnapshot[]): PersistedShellSnapshot {
  return {
    workspaces: sortWorkspaces(primarySurfaces.map(mapPrimarySurfaceToWorkspace)),
    customAgents: [],
    userDock: { ...DEFAULT_USER_DOCK },
  };
}

export function hydrateWorkspaceState(
  rawSnapshot: string | null | undefined,
  primarySurfaces: ShellRouteSnapshot[],
): PersistedShellSnapshot {
  if (!rawSnapshot) {
    return createDefaultSnapshot(primarySurfaces);
  }

  try {
    const parsed = JSON.parse(rawSnapshot) as unknown;
    if (!isRecord(parsed)) {
      return createDefaultSnapshot(primarySurfaces);
    }

    return {
      workspaces: normalizeWorkspaces(parsed.workspaces, primarySurfaces),
      customAgents: normalizeCustomAgents(parsed.customAgents),
      userDock: normalizeUserDock(parsed.userDock),
    };
  } catch {
    return createDefaultSnapshot(primarySurfaces);
  }
}

export function readPersistedShellSnapshot(primarySurfaces: ShellRouteSnapshot[]): PersistedShellSnapshot {
  if (typeof globalThis.localStorage === "undefined") {
    return createDefaultSnapshot(primarySurfaces);
  }
  return hydrateWorkspaceState(globalThis.localStorage.getItem(STORAGE_KEY), primarySurfaces);
}

export function writePersistedShellSnapshot(snapshot: PersistedShellSnapshot) {
  if (typeof globalThis.localStorage === "undefined") {
    return;
  }
  globalThis.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
}
