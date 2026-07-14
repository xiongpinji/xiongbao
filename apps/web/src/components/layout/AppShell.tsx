import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { resolveShellRoute } from "../../shell/shellRoutes";
import { useShellActions } from "../../shell/useShellStore";
import AmbientAurora from "../effects/AmbientAurora";
import CollapsedRail from "./CollapsedRail";
import ShellContextPanel from "./ShellContextPanel";
import TopBar from "./TopBar";
import WorkspaceSidebar from "./WorkspaceSidebar";

export default function AppShell({ children }: { children: ReactNode }) {
  const [workspaceCollapsed, setWorkspaceCollapsed] = useState(false);
  const location = useLocation();
  const { syncRoute } = useShellActions();

  useEffect(() => {
    syncRoute(resolveShellRoute(location.pathname, location.search));
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
