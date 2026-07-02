import type { ShellRouteSnapshot, ShellTaskKind, ShellTaskStatus } from "./shellRoutes.ts";

export type WorkspaceKind = "task" | "project" | "agent";

export interface WorkspaceSurface {
  taskId: string;
  taskKind: ShellTaskKind;
  route: string;
  title: string;
  subtitle: string;
  status: ShellTaskStatus;
  badge?: string;
  pinned: boolean;
  isPrimary: boolean;
}

export interface WorkspaceRecord {
  id: string;
  kind: WorkspaceKind;
  name: string;
  description: string;
  pinned: boolean;
  createdAt: number;
  updatedAt: number;
  surface: WorkspaceSurface | null;
}

export interface CreateWorkspaceInput {
  id: string;
  kind: WorkspaceKind;
  name?: string;
  description?: string;
  pinned?: boolean;
  surface?: WorkspaceSurface | null;
  timestamp?: number;
  createdAt?: number;
  updatedAt?: number;
}

export interface CustomAgentPersona {
  baseRole: string;
  tone?: string;
  prompt?: string;
  greeting?: string;
  tags?: string[];
}

export interface CustomAgentProfile {
  id: string;
  name: string;
  description: string;
  persona: CustomAgentPersona;
  createdAt: number;
  updatedAt: number;
}

export interface CreateCustomAgentProfileInput {
  id: string;
  name?: string;
  description?: string;
  persona: CustomAgentPersona;
  timestamp?: number;
}

const FALLBACK_WORKSPACE_NAMES: Record<WorkspaceKind, string> = {
  task: "未命名任务",
  project: "未命名项目",
  agent: "未命名智能体",
};

function normalizeLabel(value: string | undefined, fallback: string) {
  const nextValue = value?.trim();
  return nextValue ? nextValue : fallback;
}

function normalizeDescription(value: string | undefined) {
  return value?.trim() ?? "";
}

export function createWorkspaceSurface(surface: ShellRouteSnapshot): WorkspaceSurface {
  return {
    taskId: surface.taskId,
    taskKind: surface.kind,
    route: surface.route,
    title: surface.title,
    subtitle: surface.subtitle,
    status: surface.status,
    badge: surface.badge,
    pinned: surface.pinned,
    isPrimary: surface.isPrimary,
  };
}

export function createWorkspace(input: CreateWorkspaceInput): WorkspaceRecord {
  const timestamp = input.timestamp ?? Date.now();
  const createdAt = input.createdAt ?? timestamp;
  const updatedAt = input.updatedAt ?? timestamp;
  return {
    id: input.id,
    kind: input.kind,
    name: normalizeLabel(input.name, FALLBACK_WORKSPACE_NAMES[input.kind]),
    description: normalizeDescription(input.description),
    pinned: input.pinned ?? input.surface?.pinned ?? false,
    createdAt,
    updatedAt,
    surface: input.surface ?? null,
  };
}

export function renameWorkspace(workspace: WorkspaceRecord, nextName: string, timestamp = Date.now()): WorkspaceRecord {
  const normalizedName = nextName.trim();
  if (!normalizedName || normalizedName === workspace.name) {
    return workspace;
  }

  return {
    ...workspace,
    name: normalizedName,
    updatedAt: timestamp,
  };
}

export function sortWorkspaces(workspaces: WorkspaceRecord[]): WorkspaceRecord[] {
  return [...workspaces].sort((left, right) => {
    if (left.pinned !== right.pinned) {
      return left.pinned ? -1 : 1;
    }
    if (left.updatedAt !== right.updatedAt) {
      return right.updatedAt - left.updatedAt;
    }
    if (left.createdAt !== right.createdAt) {
      return right.createdAt - left.createdAt;
    }
    return left.name.localeCompare(right.name, "zh-CN");
  });
}

export function createCustomAgentProfile(input: CreateCustomAgentProfileInput): CustomAgentProfile {
  const timestamp = input.timestamp ?? Date.now();
  return {
    id: input.id,
    name: normalizeLabel(input.name, FALLBACK_WORKSPACE_NAMES.agent),
    description: normalizeDescription(input.description),
    persona: {
      ...input.persona,
      baseRole: input.persona.baseRole,
    },
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}
