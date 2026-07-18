import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
} from "lucide-react";
import { useShellActions, useShellNavigation } from "../../shell/useShellStore";

const settingsShortcuts = [
  { label: "常规", section: "general" },
  { label: "模型设置", section: "models" },
  { label: "技能", section: "skills" },
  { label: "索引库", section: "index" },
  { label: "使用统计", section: "usage" },
] as const;

export default function WorkspaceSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const location = useLocation();
  const navigation = useShellNavigation();
  const { resetChatSession, setCommandPaletteOpen } = useShellActions();

  const goalBoardItem = navigation.find((item) => item.taskId === "goal-board");
  const workflowItem = navigation.find((item) => item.taskId === "workflows");
  const settingsItem = navigation.find((item) => item.taskId === "settings");
  const sessions = navigation.filter((item) => item.taskId !== "settings");

  if (collapsed) {
    return (
      <button
        type="button"
        title="展开工作区"
        onClick={onToggle}
        className="flex h-screen w-9 shrink-0 items-start justify-center border-r border-white/[0.07] bg-black/50 pt-4 text-neutral-500 backdrop-blur-2xl hover:text-white"
      >
        <PanelLeftOpen size={18} />
      </button>
    );
  }

  return (
    <aside className="flex h-screen w-80 shrink-0 flex-col border-r border-white/[0.07] bg-black/62 text-neutral-200 backdrop-blur-2xl">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="xagent-brand-logo h-10 w-10">
            <img src="/assets/xiongbao-logo.png" alt="熊宝智能体系统" />
          </div>
          <div className="min-w-0 flex-1 pr-2">
            <div className="truncate text-sm font-semibold text-white">熊宝智能体系统</div>
            <div className="truncate text-[11px] leading-4 text-neutral-500">Xiongbao Agent System</div>
          </div>
        </div>
        <button
          type="button"
          title="折叠工作区"
          onClick={onToggle}
          className="rounded-lg p-2 text-neutral-500 transition hover:bg-white/[0.06] hover:text-white"
        >
          <PanelLeftClose size={17} />
        </button>
      </div>

      <div className="space-y-2 border-y border-white/[0.07] p-3">
        <Link
          to="/chat"
          onClick={() => resetChatSession()}
          className="gold-button flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left"
        >
          <span className="flex items-center gap-2"><MessageSquarePlus size={16} />新建会话</span>
          <span className="rounded-md bg-black/20 px-2 py-0.5 text-xs text-[#fff0bf]">Ctrl+N</span>
        </Link>
        <button
          type="button"
          onClick={() => setCommandPaletteOpen(true)}
          className="xagent-nav-item flex w-full items-center justify-between px-3 py-2 text-left text-sm"
        >
          <span className="flex items-center gap-2"><Search size={15} />搜索</span>
          <span className="text-xs text-neutral-600">Ctrl+K</span>
        </button>
        {goalBoardItem && (
          <PrimarySurfaceLink
            to={goalBoardItem.preferredRoute}
            label={goalBoardItem.title}
            subtitle={goalBoardItem.subtitle}
            active={goalBoardItem.active}
          />
        )}
        {workflowItem && (
          <PrimarySurfaceLink
            to={workflowItem.preferredRoute}
            label={workflowItem.title}
            subtitle={workflowItem.subtitle}
            active={workflowItem.active}
          />
        )}
        <Link
          to="/agents"
          className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
            location.pathname === "/agents" ? "xagent-nav-active" : "xagent-nav-item"
          }`}
        >
          <Bot size={15} />智能体角色
        </Link>
      </div>

      <div className="xagent-scrollbar flex-1 overflow-auto p-3">
        <div className="mb-2 flex items-center justify-between px-1 text-xs font-medium text-neutral-500">
          <span>会话</span>
          <span>Today</span>
        </div>
        <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.018]">
          {sessions.map((project) => (
            <Link
              key={project.taskId}
              to={project.preferredRoute}
              className={`block border-b border-white/[0.055] px-4 py-3 text-sm transition last:border-b-0 hover:bg-white/[0.045] ${
                project.active ? "bg-white/[0.055] text-white" : "text-neutral-300"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="truncate font-medium">{project.title}</div>
                <span className="shrink-0 text-xs text-neutral-500">{project.badge ?? "Surface"}</span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-3 text-xs">
                <span className="truncate text-neutral-600">{project.subtitle}</span>
                <span className="shrink-0 text-[#d6ad62]">{project.active ? "当前" : "可切换"}</span>
              </div>
            </Link>
          ))}
        </div>
        <div className="mt-4 rounded-2xl border border-dashed border-white/[0.08] bg-black/18 p-4 text-sm leading-6 text-neutral-500">
          Goal Board、工作流与对话会在统一 shell 中保留最近上下文，右侧 Context 同步显示当前 surface。
        </div>
      </div>

      <UserRow settingsRoute={settingsItem?.preferredRoute ?? "/settings"} />
    </aside>
  );
}

function PrimarySurfaceLink({
  to,
  label,
  subtitle,
  active,
}: {
  to: string;
  label: string;
  subtitle: string;
  active: boolean;
}) {
  return (
    <Link
      to={to}
      className={`block rounded-2xl px-3 py-2.5 text-left transition ${
        active ? "xagent-nav-active" : "xagent-nav-item"
      }`}
    >
      <div className="text-sm font-medium">{label}</div>
      <div className="mt-1 text-xs text-neutral-500">{subtitle}</div>
    </Link>
  );
}

function UserRow({ settingsRoute }: { settingsRoute: string }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    function handler(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={rootRef} className="relative border-t border-white/[0.07] p-3">
      <div className="xagent-surface-subtle flex items-center justify-between px-3 py-2">
        <div>
          <div className="text-sm font-semibold text-white">Xiongpinji</div>
          <div className="text-xs text-neutral-500">当前用户</div>
        </div>
        <button
          type="button"
          title="设置"
          onClick={() => setOpen((value) => !value)}
          className={`rounded-lg p-2 transition-colors ${open ? "bg-[#21180c] text-[#f1c96f]" : "text-neutral-500 hover:bg-white/[0.06] hover:text-white"}`}
        >
          <Settings size={17} />
        </button>
      </div>

      {open && (
        <div className="xagent-surface absolute bottom-16 left-3 z-30 w-60 p-1">
          {settingsShortcuts.map((item) => (
            <button
              key={item.section}
              type="button"
              onClick={() => {
                setOpen(false);
                navigate(`/settings?section=${item.section}`);
              }}
              className="block w-full rounded-xl px-3 py-2 text-left text-sm text-neutral-200 hover:bg-white/[0.06] hover:text-white"
            >
              {item.label}
            </button>
          ))}
          <div className="my-1 h-px bg-neutral-800" />
          <Link
            to={settingsRoute}
            onClick={() => setOpen(false)}
            className="block w-full rounded-xl px-3 py-2 text-left text-sm text-white hover:bg-white/[0.06]"
          >
            打开设置中心
          </Link>
        </div>
      )}
    </div>
  );
}
