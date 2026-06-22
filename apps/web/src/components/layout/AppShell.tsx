import { useState, type ReactNode } from "react";
import CollapsedRail from "./CollapsedRail";
import TopBar from "./TopBar";
import WorkspaceSidebar from "./WorkspaceSidebar";

export default function AppShell({ children }: { children: ReactNode }) {
  const [workspaceCollapsed, setWorkspaceCollapsed] = useState(false);

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-neutral-950 text-neutral-100">
      <CollapsedRail />
      <WorkspaceSidebar
        collapsed={workspaceCollapsed}
        onToggle={() => setWorkspaceCollapsed((value) => !value)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="min-h-0 flex-1 overflow-auto bg-neutral-950">{children}</main>
      </div>
    </div>
  );
}
