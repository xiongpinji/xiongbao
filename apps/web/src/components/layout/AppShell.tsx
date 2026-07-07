import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import {
  createRunShellRoute,
  PRIMARY_SHELL_SURFACES,
  type ShellRouteSnapshot,
} from "../../shell/shellRoutes";
import { useShellActions } from "../../shell/useShellStore";
import AmbientAurora from "../effects/AmbientAurora";
import CollapsedRail from "./CollapsedRail";
import ShellContextPanel from "./ShellContextPanel";
import TopBar from "./TopBar";
import WorkspaceSidebar from "./WorkspaceSidebar";

function routeSnapshot(pathname: string, search: string): ShellRouteSnapshot {
  const params = new URLSearchParams(search);

  if (pathname.startsWith("/runs/")) {
    const runId = decodeURIComponent(pathname.split("/").pop() ?? "run");
    return createRunShellRoute(runId, { source: "run" });
  }

  if (pathname === "/professional") {
    const mode = params.get("mode") === "workflow" ? "workflow" : "drama";
    return {
      taskId: mode === "workflow" ? "workflows" : "creative",
      kind: mode === "workflow" ? "workflow" : "creative",
      route: `/professional?mode=${mode}`,
      title: mode === "workflow" ? "工作流" : "短剧工厂",
      subtitle: mode === "workflow" ? "编排任务、审批节点与执行状态" : "从剧本到分镜、生成与剪辑的专业流程",
      badge: "专业模式",
      pinned: true,
      isPrimary: true,
      status: "ready",
    };
  }

  if (pathname === "/editor") {
    return {
      taskId: "editor",
      kind: "creative",
      route: "/editor",
      title: "剪辑工作台",
      subtitle: "时间线、素材轨道与剪映草稿导出",
      badge: "Studio",
      pinned: false,
      isPrimary: false,
      status: "ready",
    };
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
  if (primary) return primary;

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

export default function AppShell({ children }: { children: ReactNode }) {
  const [workspaceCollapsed, setWorkspaceCollapsed] = useState(false);
  const location = useLocation();
  const { syncRoute } = useShellActions();

  useEffect(() => {
    syncRoute(routeSnapshot(location.pathname, location.search));
  }, [location.pathname, location.search, syncRoute]);

  return (
    <div className="xagent-app-bg relative flex h-[100dvh] overflow-hidden text-neutral-100">
      <AmbientAurora />
      <div className="relative z-10 flex h-full shrink-0">
        <CollapsedRail />
      </div>
      <div className="relative z-10 hidden lg:block">
        <WorkspaceSidebar
          collapsed={workspaceCollapsed}
          onToggle={() => setWorkspaceCollapsed((value) => !value)}
        />
      </div>
      <div className="relative z-10 flex min-w-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <main className="xagent-scrollbar min-h-0 flex-1 overflow-auto bg-transparent">{children}</main>
        </div>
        <ShellContextPanel />
      </div>
    </div>
  );
}
