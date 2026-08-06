export type ShellTaskKind = "chat" | "workflow" | "creative" | "agent" | "settings" | "run";

export type ShellTaskStatus = "ready" | "running" | "attention";

export interface ShellRouteSnapshot {
  taskId: string;
  kind: ShellTaskKind;
  route: string;
  title: string;
  subtitle: string;
  badge?: string;
  pinned: boolean;
  isPrimary: boolean;
  status: ShellTaskStatus;
}

export interface ShellTrackedTaskLike {
  id: string;
  route: string;
}

export interface ShellNavigationItem extends ShellRouteSnapshot {
  preferredRoute: string;
  active: boolean;
}

const RUN_ROUTE_PATTERN = /^\/runs\/[^/]+$/;
const GOAL_BOARD_TASK_PREFIX = "goal-board:";

export function isRunRoute(route: string) {
  return RUN_ROUTE_PATTERN.test(route);
}

export function createRunShellRoute(
  runId: string,
  options: {
    source?: "chat" | "workflow" | "creative" | "run";
    title?: string;
    subtitle?: string;
    status?: ShellTaskStatus;
  } = {},
): ShellRouteSnapshot {
  const sourceLabel =
    options.source === "workflow"
      ? "工作流"
      : options.source === "creative"
        ? "短剧工厂"
        : options.source === "run"
          ? "运行"
          : "对话";
  const encodedRunId = encodeURIComponent(runId);

  return {
    taskId: `run:${runId}`,
    kind: "run",
    route: `/runs/${encodedRunId}`,
    title: options.title?.trim() || `${sourceLabel}运行`,
    subtitle: options.subtitle?.trim() || `${sourceLabel}运行详情 · ${runId}`,
    badge: "运行",
    pinned: false,
    isPrimary: false,
    status: options.status ?? "ready",
  };
}

export function createGoalBoardShellRoute(goalId?: string | null): ShellRouteSnapshot {
  const normalizedGoalId = goalId?.trim() ?? "";
  const encodedGoalId = normalizedGoalId ? encodeURIComponent(normalizedGoalId) : "";

  return {
    taskId: normalizedGoalId ? `${GOAL_BOARD_TASK_PREFIX}${normalizedGoalId}` : "goal-board",
    kind: "workflow",
    route: normalizedGoalId ? `/goal-board?goalId=${encodedGoalId}` : "/goal-board",
    title: "目标任务板",
    subtitle: normalizedGoalId ? `持续推进当前交付主目标 · ${normalizedGoalId}` : "持续推进当前交付主目标",
    badge: "PM",
    pinned: true,
    isPrimary: true,
    status: "ready",
  };
}

export const PRIMARY_SHELL_SURFACES: ShellRouteSnapshot[] = [
  {
    taskId: "chat",
    kind: "chat",
    route: "/chat",
    title: "对话",
    subtitle: "统一工作区中的主对话上下文",
    badge: "工作区",
    pinned: true,
    isPrimary: true,
    status: "ready",
  },
  {
    taskId: "goal-board",
    kind: "workflow",
    route: "/goal-board",
    title: "目标任务板",
    subtitle: "持续推进当前交付主目标",
    badge: "PM",
    pinned: true,
    isPrimary: true,
    status: "ready",
  },
  {
    taskId: "workflows",
    kind: "workflow",
    route: "/professional?mode=workflow",
    title: "工作流",
    subtitle: "编排任务、审批节点与执行状态",
    badge: "专业模式",
    pinned: true,
    isPrimary: true,
    status: "ready",
  },
  {
    taskId: "development-tasks",
    kind: "workflow",
    route: "/development-tasks",
    title: "开发任务",
    subtitle: "审查隔离产物并受控应用代码变更",
    badge: "Git",
    pinned: true,
    isPrimary: true,
    status: "ready",
  },
  {
    taskId: "agents",
    kind: "agent",
    route: "/agents",
    title: "智能体",
    subtitle: "浏览当前可用的角色与能力",
    badge: "角色",
    pinned: true,
    isPrimary: true,
    status: "ready",
  },
  {
    taskId: "settings",
    kind: "settings",
    route: "/settings",
    title: "设置",
    subtitle: "集中管理模型、技能与索引配置",
    badge: "配置",
    pinned: true,
    isPrimary: true,
    status: "ready",
  },
];

function normalizeSurfaceTaskId(taskId: string | null | undefined) {
  if (!taskId) {
    return null;
  }

  if (taskId === "goal-board" || taskId.startsWith(GOAL_BOARD_TASK_PREFIX)) {
    return "goal-board";
  }

  return taskId;
}

function createPrimarySurfaceSnapshot(surface: ShellRouteSnapshot, pathname: string, search: string): ShellRouteSnapshot {
  if (!search) {
    return surface;
  }

  return {
    ...surface,
    route: `${pathname}${search}`,
  };
}

export function isShellSurfaceActive(surfaceTaskId: string, currentTaskId: string | null | undefined) {
  return normalizeSurfaceTaskId(currentTaskId) === surfaceTaskId;
}

export function getPreferredSurfaceRoute(
  surface: ShellRouteSnapshot,
  tasks: ShellTrackedTaskLike[],
  currentTaskId?: string | null,
) {
  if (currentTaskId && isShellSurfaceActive(surface.taskId, currentTaskId)) {
    const activeTask = tasks.find((task) => task.id === currentTaskId);
    if (activeTask) {
      return activeTask.route;
    }
  }

  const matchedTask = tasks.find((task) => isShellSurfaceActive(surface.taskId, task.id));
  return matchedTask?.route ?? surface.route;
}

export function buildPrimaryNavigation(
  tasks: ShellTrackedTaskLike[],
  currentTaskId?: string | null,
): ShellNavigationItem[] {
  return PRIMARY_SHELL_SURFACES.map((surface) => ({
    ...surface,
    preferredRoute: getPreferredSurfaceRoute(surface, tasks, currentTaskId),
    active: isShellSurfaceActive(surface.taskId, currentTaskId),
  }));
}

export function resolveShellRoute(pathname: string, search: string): ShellRouteSnapshot {
  const params = new URLSearchParams(search);

  if (pathname.startsWith("/runs/")) {
    const runId = decodeURIComponent(pathname.split("/").pop() ?? "run");
    return createRunShellRoute(runId, { source: "run" });
  }

  if (pathname === "/professional") {
    return {
      taskId: "workflows",
      kind: "workflow",
      route: "/professional?mode=workflow",
      title: "工作流",
      subtitle: "编排任务、审批节点与执行状态",
      badge: "专业模式",
      pinned: true,
      isPrimary: true,
      status: "ready",
    };
  }

  if (pathname === "/goal-board") {
    return createGoalBoardShellRoute(params.get("goalId"));
  }

  if (pathname === "/memory") {
    return {
      taskId: "memory",
      kind: "settings",
      route: "/memory",
      title: "长期记忆与知识库",
      subtitle: "项目知识库、智能体专属记忆与隔离检索",
      badge: "Memory",
      pinned: false,
      isPrimary: false,
      status: "ready",
    };
  }

  if (pathname === "/open-source") {
    return {
      taskId: "open-source",
      kind: "settings",
      route: "/open-source",
      title: "开源补齐方案发现",
      subtitle: "能力缺口、仓库比选、许可证与接入策略",
      badge: "Scout",
      pinned: false,
      isPrimary: false,
      status: "ready",
    };
  }

  const normalizedPathname = pathname === "/home" ? "/chat" : pathname;
  const primary = PRIMARY_SHELL_SURFACES.find((surface) => surface.route.split("?")[0] === normalizedPathname);
  if (primary) {
    return createPrimarySurfaceSnapshot(primary, normalizedPathname, search);
  }

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
  };
}
