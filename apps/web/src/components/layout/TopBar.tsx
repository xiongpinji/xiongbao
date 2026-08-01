import { useLocation } from "react-router-dom";
import { PanelLeftOpen, PanelRight, Zap } from "lucide-react";
import { getLLMConfig } from "../../api";
import { useEffect, useState } from "react";

const PAGE_TITLES: Record<string, string> = {
  "/chat": "对话",
  "/home": "对话",
  "/agents": "智能体",
  "/goal-board": "目标看板",
  "/professional": "工作流",
  "/settings": "设置",
  "/billing": "计费",
  "/audit": "审计",
  "/memory": "记忆库",
  "/open-source": "开源发现",
  "/editor": "剪辑台",
};

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
  const [model, setModel] = useState("");

  useEffect(() => {
    getLLMConfig()
      .then((cfg) => setModel(cfg.default_model))
      .catch(() => {});
  }, []);

  const title = PAGE_TITLES[location.pathname] ?? "X-Agent";

  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-white/[0.06] bg-[#111111] px-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          title="切换侧边栏"
          onClick={onToggleSidebar}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 transition hover:bg-white/[0.06] hover:text-white"
        >
          <PanelLeftOpen size={16} />
        </button>
        <span className="text-sm font-medium text-neutral-200">{title}</span>
      </div>

      <div className="flex items-center gap-1.5">
        {model && (
          <span className="flex items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.03] px-2.5 py-1 text-xs text-neutral-400">
            <Zap size={11} className="text-amber-400" />
            {model}
          </span>
        )}
        <button
          type="button"
          title="上下文面板"
          onClick={onToggleContext}
          className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${
            contextOpen
              ? "bg-white/[0.08] text-white"
              : "text-neutral-500 hover:bg-white/[0.06] hover:text-white"
          }`}
        >
          <PanelRight size={16} />
        </button>
      </div>
    </header>
  );
}
