import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import type { Edge, Node } from "reactflow";
import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";
import type { AgentRun, WorkflowView } from "../api/index.ts";
import {
  createCustomAgentProfile,
  createWorkspace,
  type CreateCustomAgentProfileInput,
  type CreateWorkspaceInput,
  renameWorkspace,
  sortWorkspaces,
  type CustomAgentProfile,
  type WorkspaceRecord,
} from "./workspaceModels.ts";
import {
  readPersistedShellSnapshot,
  writePersistedShellSnapshot,
  type PersistedUserDockProfile,
} from "./workspaceStorage.ts";
import {
  createRunShellRoute,
  PRIMARY_SHELL_SURFACES,
  type ShellRouteSnapshot,
  type ShellTaskKind,
  type ShellTaskStatus,
} from "./shellRoutes.ts";

export interface ShellTaskSummary {
  id: string;
  kind: ShellTaskKind;
  title: string;
  subtitle: string;
  route: string;
  status: ShellTaskStatus;
  badge?: string;
  pinned: boolean;
  isPrimary: boolean;
  updatedAt: number;
}

export interface ShellActivityItem {
  id: string;
  taskId: string;
  title: string;
  detail: string;
  tone: "info" | "success" | "warning" | "error";
  timestamp: number;
}

export interface ShellSessionState {
  id: string;
  label: string;
  startedAt: number;
  currentProject: string;
}

export interface ShellWorkflowStepDraft {
  id: string;
  name: string;
  role: string;
  goal: string;
  approverRole: string;
  approvalMessage: string;
}

export interface ShellWorkflowNodeData {
  label: string;
}

export type ShellWorkflowNode = Node<ShellWorkflowNodeData>;
export type ShellWorkflowEdge = Edge;

export interface ShellChatTaskState {
  goal: string;
  loading: boolean;
  run: AgentRun | null;
  streamText: string;
  error: string | null;
}

export interface ShellWorkflowTaskState {
  name: string;
  view: WorkflowView | null;
  error: string | null;
  loading: boolean;
  steps: ShellWorkflowStepDraft[];
  nodes: ShellWorkflowNode[];
  edges: ShellWorkflowEdge[];
}

type StatePatch<T> = Partial<T> | ((current: T) => T);

interface ShellState {
  session: ShellSessionState;
  tasks: ShellTaskSummary[];
  currentContext: ShellTaskSummary | null;
  sidebarCollapsed: boolean;
  threadPanelOpen: boolean;
  commandPaletteOpen: boolean;
  activity: ShellActivityItem[];
  workspaces: WorkspaceRecord[];
  customAgents: CustomAgentProfile[];
  userDock: PersistedUserDockProfile;
  chatTaskState: Record<string, ShellChatTaskState>;
  workflowTaskState: Record<string, ShellWorkflowTaskState>;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setThreadPanelOpen: (open: boolean) => void;
  toggleThreadPanel: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  syncRoute: (snapshot: ShellRouteSnapshot) => void;
  syncRunTask: (
    runId: string,
    options?: {
      source?: "chat" | "workflow" | "creative" | "run";
      title?: string;
      subtitle?: string;
      status?: ShellTaskStatus;
    },
  ) => void;
  setCurrentContext: (context: Omit<ShellTaskSummary, "updatedAt">) => void;
  appendActivity: (entry: Omit<ShellActivityItem, "id" | "timestamp"> & { timestamp?: number }) => void;
  createWorkspaceRecord: (input: CreateWorkspaceInput) => WorkspaceRecord;
  renameWorkspaceRecord: (workspaceId: string, nextName: string) => void;
  saveCustomAgentProfile: (input: CreateCustomAgentProfileInput) => CustomAgentProfile;
  patchChatTaskState: (taskId: string, patch: StatePatch<ShellChatTaskState>) => void;
  patchWorkflowTaskState: (taskId: string, patch: StatePatch<ShellWorkflowTaskState>) => void;
}

const MAX_ACTIVITY_ITEMS = 40;

const FLOW_NODE_STYLE = {
  background: "#171717",
  color: "#fafafa",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 16,
  padding: 10,
  width: 220,
  boxShadow: "0 12px 28px rgba(0,0,0,0.22)",
};

function createWorkflowStepId() {
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

function applyPatch<T>(current: T, patch: StatePatch<T>): T {
  if (typeof patch === "function") {
    return patch(current);
  }
  return { ...current, ...patch };
}

function persistWorkspaceSnapshot(state: Pick<ShellState, "workspaces" | "customAgents" | "userDock">) {
  writePersistedShellSnapshot({
    workspaces: state.workspaces,
    customAgents: state.customAgents,
    userDock: state.userDock,
  });
}

export function createShellWorkflowNode(id: string, label: string, index: number): ShellWorkflowNode {
  return {
    id,
    type: index === 0 ? "input" : "default",
    position: { x: 90 + index * 240, y: 120 + (index % 2) * 80 },
    data: { label },
    style: FLOW_NODE_STYLE,
  };
}

export function createShellWorkflowStep(index: number): ShellWorkflowStepDraft {
  return {
    id: createWorkflowStepId(),
    name: `步骤${index + 1}`,
    role: "general",
    goal: "",
    approverRole: "",
    approvalMessage: "",
  };
}

function makeDefaultWorkflowSteps(): ShellWorkflowStepDraft[] {
  return [createShellWorkflowStep(0)];
}

function makeDefaultChatTaskState(): ShellChatTaskState {
  return {
    goal: "",
    loading: false,
    run: null,
    streamText: "",
    error: null,
  };
}

function makeDefaultWorkflowTaskState(): ShellWorkflowTaskState {
  const steps = makeDefaultWorkflowSteps();
  return {
    name: "新工作流",
    view: null,
    error: null,
    loading: false,
    steps,
    nodes: [createShellWorkflowNode(steps[0].id, `步骤1 · ${steps[0].name}`, 0)],
    edges: [],
  };
}

const FALLBACK_CHAT_TASK_STATE = makeDefaultChatTaskState();
const FALLBACK_WORKFLOW_TASK_STATE = makeDefaultWorkflowTaskState();

function ensureRouteTaskState(state: ShellState, snapshot: ShellRouteSnapshot): Partial<ShellState> | null {
  if (snapshot.kind === "chat" && !state.chatTaskState.chat) {
    return {
      chatTaskState: {
        ...state.chatTaskState,
        chat: makeDefaultChatTaskState(),
      },
    };
  }

  if (snapshot.taskId === "workflows" && !state.workflowTaskState.workflows) {
    return {
      workflowTaskState: {
        ...state.workflowTaskState,
        workflows: makeDefaultWorkflowTaskState(),
      },
    };
  }

  return null;
}

function makeBaseTasks(): ShellTaskSummary[] {
  const now = Date.now();
  return PRIMARY_SHELL_SURFACES.map((surface, index) => ({
    id: surface.taskId,
    kind: surface.kind,
    title: surface.title,
    subtitle: surface.subtitle,
    route: surface.route,
    status: surface.status,
    badge: surface.badge,
    pinned: surface.pinned,
    isPrimary: surface.isPrimary,
    updatedAt: now - index,
  }));
}

function createSessionState(): ShellSessionState {
  const startedAt = Date.now();
  return {
    id: `shell-${startedAt}`,
    label: `当前会话 ${new Date(startedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`,
    startedAt,
    currentProject: "xiong bao / xagent / apps/web",
  };
}

function sortTasks(tasks: ShellTaskSummary[]) {
  return [...tasks].sort((a, b) => {
    if (a.isPrimary !== b.isPrimary) return a.isPrimary ? -1 : 1;
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    return b.updatedAt - a.updatedAt;
  });
}

function createActivityEntry(
  state: ShellState,
  entry: Omit<ShellActivityItem, "id" | "timestamp"> & { timestamp?: number },
): ShellActivityItem {
  return {
    ...entry,
    id: `${entry.taskId}-${Date.now()}-${state.activity.length}`,
    timestamp: entry.timestamp ?? Date.now(),
  };
}

export type ShellStore = ReturnType<typeof createShellStore>;

export function createShellStore() {
  const initialTasks = makeBaseTasks();
  const persistedSnapshot = readPersistedShellSnapshot(PRIMARY_SHELL_SURFACES);

  return createStore<ShellState>()((set) => ({
    session: createSessionState(),
    tasks: initialTasks,
    currentContext: initialTasks[0] ?? null,
    sidebarCollapsed: false,
    threadPanelOpen: true,
    commandPaletteOpen: false,
    activity: [
      {
        id: "boot",
        taskId: "chat",
        title: "Shell 已就绪",
        detail: "当前工作台状态已就绪，可继续进入正式页面执行任务。",
        tone: "info",
        timestamp: Date.now(),
      },
    ],
    workspaces: persistedSnapshot.workspaces,
    customAgents: persistedSnapshot.customAgents,
    userDock: persistedSnapshot.userDock,
    chatTaskState: {
      chat: makeDefaultChatTaskState(),
    },
    workflowTaskState: {
      workflows: makeDefaultWorkflowTaskState(),
    },
    setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
    toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
    setThreadPanelOpen: (open) => set({ threadPanelOpen: open }),
    toggleThreadPanel: () => set((state) => ({ threadPanelOpen: !state.threadPanelOpen })),
    setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
    syncRunTask: (runId, options) => {
      set((state) => {
        const snapshot = createRunShellRoute(runId, options);
        const now = Date.now();
        const nextTask: ShellTaskSummary = {
          id: snapshot.taskId,
          kind: snapshot.kind,
          title: snapshot.title,
          subtitle: snapshot.subtitle,
          route: snapshot.route,
          status: snapshot.status,
          badge: snapshot.badge,
          pinned: snapshot.pinned,
          isPrimary: snapshot.isPrimary,
          updatedAt: now,
        };
        const existingTasks = state.tasks.filter((task) => task.id !== snapshot.taskId);

        return {
          tasks: sortTasks([nextTask, ...existingTasks]),
          currentContext: nextTask,
        };
      });
    },
    syncRoute: (snapshot) => {
      set((state) => {
        const now = Date.now();
        const nextTask: ShellTaskSummary = {
          id: snapshot.taskId,
          kind: snapshot.kind,
          title: snapshot.title,
          subtitle: snapshot.subtitle,
          route: snapshot.route,
          status: snapshot.status,
          badge: snapshot.badge,
          pinned: snapshot.pinned,
          isPrimary: snapshot.isPrimary,
          updatedAt: now,
        };

        const existingTasks = state.tasks.filter((task) => task.id !== snapshot.taskId);
        const routeTaskState = ensureRouteTaskState(state, snapshot);

        return {
          tasks: [nextTask, ...sortTasks(existingTasks)],
          currentContext: nextTask,
          ...(routeTaskState ?? {}),
        };
      });
    },
    setCurrentContext: (context) => {
      set((state) => {
        const nextTask: ShellTaskSummary = {
          ...context,
          updatedAt: Date.now(),
        };
        return {
          tasks: [nextTask, ...state.tasks.filter((task) => task.id !== nextTask.id)],
          currentContext: nextTask,
        };
      });
    },
    appendActivity: (entry) => {
      set((state) => {
        const nextEntry = createActivityEntry(state, entry);
        return {
          activity: [nextEntry, ...state.activity].slice(0, MAX_ACTIVITY_ITEMS),
        };
      });
    },
    createWorkspaceRecord: (input) => {
      const workspace = createWorkspace(input);
      set((state) => {
        const workspaces = sortWorkspaces([
          workspace,
          ...state.workspaces.filter((record) => record.id !== workspace.id),
        ]);
        persistWorkspaceSnapshot({
          workspaces,
          customAgents: state.customAgents,
          userDock: state.userDock,
        });
        return { workspaces };
      });
      return workspace;
    },
    renameWorkspaceRecord: (workspaceId, nextName) => {
      set((state) => {
        const currentWorkspace = state.workspaces.find((workspace) => workspace.id === workspaceId);
        if (!currentWorkspace) {
          return {};
        }

        const renamedWorkspace = renameWorkspace(currentWorkspace, nextName);
        if (renamedWorkspace === currentWorkspace) {
          return {};
        }

        const workspaces = sortWorkspaces(
          state.workspaces.map((workspace) => (workspace.id === workspaceId ? renamedWorkspace : workspace)),
        );
        persistWorkspaceSnapshot({
          workspaces,
          customAgents: state.customAgents,
          userDock: state.userDock,
        });
        return { workspaces };
      });
    },
    saveCustomAgentProfile: (input) => {
      const profile = createCustomAgentProfile(input);
      set((state) => {
        const customAgents = [...state.customAgents.filter((agent) => agent.id !== profile.id), profile].sort(
          (left, right) => right.updatedAt - left.updatedAt,
        );
        persistWorkspaceSnapshot({
          workspaces: state.workspaces,
          customAgents,
          userDock: state.userDock,
        });
        return { customAgents };
      });
      return profile;
    },
    patchChatTaskState: (_taskId, patch) => {
      set((state) => ({
        chatTaskState: {
          ...state.chatTaskState,
          chat: applyPatch(state.chatTaskState.chat ?? makeDefaultChatTaskState(), patch),
        },
      }));
    },
    patchWorkflowTaskState: (_taskId, patch) => {
      set((state) => ({
        workflowTaskState: {
          ...state.workflowTaskState,
          workflows: applyPatch(
            state.workflowTaskState.workflows ?? makeDefaultWorkflowTaskState(),
            patch,
          ),
        },
      }));
    },
  }));
}

const ShellStoreContext = createContext<ShellStore | null>(null);

export function ShellStoreProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<ShellStore | null>(null);
  if (!storeRef.current) {
    storeRef.current = createShellStore();
  }

  return <ShellStoreContext.Provider value={storeRef.current}>{children}</ShellStoreContext.Provider>;
}

export function useShellStore<T>(selector: (state: ShellState) => T): T {
  const store = useContext(ShellStoreContext);
  if (!store) {
    throw new Error("useShellStore must be used within ShellStoreProvider");
  }
  return useStore(store, selector);
}

export function useShellActions() {
  return useShellStore((state) => ({
    setSidebarCollapsed: state.setSidebarCollapsed,
    toggleSidebar: state.toggleSidebar,
    setThreadPanelOpen: state.setThreadPanelOpen,
    toggleThreadPanel: state.toggleThreadPanel,
    setCommandPaletteOpen: state.setCommandPaletteOpen,
    syncRoute: state.syncRoute,
    syncRunTask: state.syncRunTask,
    setCurrentContext: state.setCurrentContext,
    appendActivity: state.appendActivity,
    createWorkspaceRecord: state.createWorkspaceRecord,
    renameWorkspaceRecord: state.renameWorkspaceRecord,
    saveCustomAgentProfile: state.saveCustomAgentProfile,
    patchChatTaskState: state.patchChatTaskState,
    patchWorkflowTaskState: state.patchWorkflowTaskState,
  }));
}

export function useShellTask(taskId: string | null | undefined) {
  return useShellStore((state) => state.tasks.find((task) => task.id === taskId) ?? null);
}

export function useShellChatTaskState(_taskId: string) {
  return useShellStore((state) => state.chatTaskState.chat ?? FALLBACK_CHAT_TASK_STATE);
}

export function useShellWorkflowTaskState(_taskId: string) {
  return useShellStore((state) => state.workflowTaskState.workflows ?? FALLBACK_WORKFLOW_TASK_STATE);
}

export function useShellDerivedState() {
  const session = useShellStore((state) => state.session);
  const tasks = useShellStore((state) => state.tasks);
  const currentContext = useShellStore((state) => state.currentContext);
  const activity = useShellStore((state) => state.activity);

  return useMemo(() => {
    const activeTask = currentContext ?? tasks[0] ?? null;
    const recentTasks = tasks
      .filter((task) => task.id !== activeTask?.id)
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, 10);
    const activeTaskActivity = activeTask
      ? activity.filter((item) => item.taskId === activeTask.id).slice(0, 10)
      : [];

    return {
      session,
      tasks,
      activeTask,
      currentContext: activeTask,
      recentTasks,
      activity,
      activeTaskActivity,
    };
  }, [activity, currentContext, session, tasks]);
}

export function useRegisterShellActivity(
  activityFactory: (() => Omit<ShellActivityItem, "id" | "timestamp"> | null) | null,
  deps: readonly unknown[],
) {
  const appendActivity = useShellStore((state) => state.appendActivity);

  useEffect(() => {
    if (!activityFactory) return;
    const item = activityFactory();
    if (!item) return;
    appendActivity(item);
  }, [activityFactory, appendActivity, ...deps]);
}
