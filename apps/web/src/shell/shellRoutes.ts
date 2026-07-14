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

const RUN_ROUTE_PATTERN = /^\/runs\/[^/]+$/;

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
    taskId: "creative",
    kind: "creative",
    route: "/creative/canvas",
    title: "短剧工厂",
    subtitle: "从剧本到分镜、生成与剪辑的专业流程",
    badge: "专业模式",
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
