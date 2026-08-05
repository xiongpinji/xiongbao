import { useLocation, useNavigate } from "react-router-dom";
import { Globe, PanelLeftOpen, Settings } from "lucide-react";

export default function TopBar({
  onToggleSidebar,
  onToggleContext,
  contextOpen,
}: {
  onToggleSidebar: () => void;
  onToggleContext: () => void;
  contextOpen: boolean;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const isChat = location.pathname === "/chat" || location.pathname === "/home";

  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-white/[0.04] bg-[#0d0d0d] px-3">
      {/* 左侧：侧栏切换 */}
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          title="切换侧边栏"
          aria-label="切换侧边栏"
          onClick={onToggleSidebar}
          className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-600 transition hover:bg-white/[0.05] hover:text-neutral-300"
        >
          <PanelLeftOpen size={15} />
        </button>
      </div>

      {/* 右侧：设置 + 上下文面板 */}
      <div className="flex items-center gap-0.5">
        {!isChat && (
          <button
            type="button"
            title="设置"
            aria-label="设置"
            onClick={() => navigate("/settings")}
            className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-600 transition hover:bg-white/[0.05] hover:text-neutral-300"
          >
            <Settings size={14} />
          </button>
        )}
        <button
          type="button"
          title="预览面板"
          aria-label="预览面板"
          onClick={onToggleContext}
          className={`flex h-7 w-7 items-center justify-center rounded-md transition ${
            contextOpen
              ? "bg-white/[0.06] text-neutral-200"
              : "text-neutral-600 hover:bg-white/[0.05] hover:text-neutral-300"
          }`}
        >
          <Globe size={14} />
        </button>
      </div>
    </header>
  );
}
