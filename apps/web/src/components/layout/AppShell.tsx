import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { resolveShellRoute } from "../../shell/shellRoutes";
import { useShellActions } from "../../shell/useShellStore";
import CommandPalette from "./CommandPalette";
import ShellContextPanel from "./ShellContextPanel";
import TopBar from "./TopBar";
import WorkspaceSidebar from "./WorkspaceSidebar";

export default function AppShell({ children }: { children: ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const location = useLocation();
  const { syncRoute } = useShellActions();

  useEffect(() => {
    syncRoute(resolveShellRoute(location.pathname, location.search));
  }, [location.pathname, location.search, syncRoute]);

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-[#0a0a0a] text-neutral-100">
      <CommandPalette />

      {/* 左侧边栏 */}
      <WorkspaceSidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
      />

      {/* 主区域 */}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
          onToggleContext={() => setContextOpen((v) => !v)}
          contextOpen={contextOpen}
        />
        <div className="flex min-h-0 flex-1">
          <main className="xagent-scrollbar min-w-0 flex-1 overflow-auto">{children}</main>
          {/* 右侧上下文面板 - 按需显示 */}
          {contextOpen && <ShellContextPanel onClose={() => setContextOpen(false)} />}
        </div>
      </div>
    </div>
  );
}
