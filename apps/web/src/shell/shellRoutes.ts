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
    taskId: "workflows",
    kind: "workflow",
    route: "/workflows",
    title: "工作流",
    subtitle: "查看编排执行与审批进度",
    badge: "编排",
    pinned: true,
    isPrimary: true,
    status: "ready",
  },
  {
    taskId: "creative",
    kind: "creative",
    route: "/creative",
    title: "短剧工厂",
    subtitle: "管理创意生产链路与媒体产出",
    badge: "创作",
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
