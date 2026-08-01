import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  CreditCard,
  Grid2X2,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  ShieldCheck,
  Target,
} from "lucide-react";
import { useShellActions, useShellNavigation } from "../../shell/useShellStore";

export default function WorkspaceSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const location = useLocation();
  const navigation = useShellNavigation();
  const { resetChatSession, setCommandPaletteOpen } = useShellActions();

  const sessions = navigation.filter(
    (item) => !["settings", "goal-board", "workflows", "agents"].includes(item.taskId),
  );

  if (collapsed) {
    return (
      <div className="flex h-full w-[52px] shrink-0 flex-col items-center border-r border-white/[0.06] bg-[#111111] py-3">
        <button
          type="button"
          title="展开侧边栏"
          onClick={onToggle}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-neutral-500 transition hover:bg-white/[0.06] hover:text-white"
        >
          <PanelLeftOpen size={17} />
        </button>
        <div className="mt-4 flex flex-col items-center gap-1">
          <Link
            to="/chat"
            onClick={resetChatSession}
            title="新建对话"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-neutral-400 transition hover:bg-white/[0.06] hover:text-white"
          >
            <MessageSquarePlus size={17} />
          </Link>
          <button
            type="button"
            title="搜索"
            onClick={() => setCommandPaletteOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-neutral-500 transition hover:bg-white/[0.06] hover:text-white"
          >
            <Search size={17} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <aside className="flex h-full w-[264px] shrink-0 flex-col border-r border-white/[0.06] bg-[#111111]">
      {/* 顶部 */}
      <div className="flex items-center justify-between px-3 py-3">
        <div className="flex items-center gap-2.5 px-1">
          <div className="h-7 w-7 overflow-hidden rounded-lg">
            <img src="/assets/xiongbao-logo.png" alt="X-Agent" className="h-full w-full object-cover" />
          </div>
          <span className="text-sm font-semibold text-white">X-Agent</span>
        </div>
        <button
          type="button"
          title="折叠侧边栏"
          onClick={onToggle}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 transition hover:bg-white/[0.06] hover:text-white"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      {/* 新建对话 */}
      <div className="px-3 pb-2">
        <Link
          to="/chat"
          onClick={resetChatSession}
          className="flex w-full items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-2.5 text-sm font-medium text-white transition hover:bg-white/[0.08]"
        >
          <MessageSquarePlus size={16} className="text-neutral-400" />
          新建对话
          <kbd className="ml-auto rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-neutral-500">⌘N</kbd>
        </Link>
      </div>

      {/* 搜索 */}
      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={() => setCommandPaletteOpen(true)}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-300"
        >
          <Search size={15} />
          搜索...
          <kbd className="ml-auto rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-neutral-600">⌘K</kbd>
        </button>
      </div>

      {/* 导航 */}
      <nav className="space-y-0.5 border-b border-white/[0.06] px-3 pb-3">
        <NavItem to="/goal-board" icon={Target} label="目标看板" active={location.pathname === "/goal-board"} />
        <NavItem to="/professional?mode=workflow" icon={Grid2X2} label="工作流" active={location.pathname === "/professional"} />
        <NavItem to="/agents" icon={Bot} label="智能体" active={location.pathname === "/agents"} />
      </nav>

      {/* 会话历史 */}
      <div className="xagent-scrollbar min-h-0 flex-1 overflow-auto px-3 py-3">
        <div className="mb-2 px-1 text-[11px] font-medium uppercase tracking-wider text-neutral-600">
          最近对话
        </div>
        <div className="space-y-0.5">
          {sessions.map((item) => (
            <Link
              key={item.taskId}
              to={item.preferredRoute}
              className={`block truncate rounded-lg px-3 py-2 text-sm transition ${
                item.active
                  ? "bg-white/[0.08] text-white"
                  : "text-neutral-400 hover:bg-white/[0.05] hover:text-neutral-200"
              }`}
            >
              {item.title}
            </Link>
          ))}
          {sessions.length === 0 && (
            <div className="px-3 py-4 text-center text-xs text-neutral-600">暂无对话记录</div>
          )}
        </div>
      </div>

      {/* 底部用户 */}
      <UserFooter />
    </aside>
  );
}

function NavItem({ to, icon: Icon, label, active }: { to: string; icon: typeof Bot; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${
        active
          ? "bg-white/[0.08] font-medium text-white"
          : "text-neutral-400 hover:bg-white/[0.05] hover:text-neutral-200"
      }`}
    >
      <Icon size={16} />
      {label}
    </Link>
  );
}

function UserFooter() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={rootRef} className="relative border-t border-white/[0.06] p-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition hover:bg-white/[0.05]"
      >
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-amber-500/20 to-orange-600/20 text-xs font-bold text-amber-300">
          X
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-white">Xiongpinji</div>
          <div className="text-[11px] text-neutral-600">Pro 计划</div>
        </div>
        <Settings size={15} className="shrink-0 text-neutral-600" />
      </button>

      {open && (
        <div className="absolute bottom-14 left-3 z-50 w-56 rounded-xl border border-white/[0.08] bg-[#1a1a1a] p-1.5 shadow-2xl">
          <MenuBtn onClick={() => { setOpen(false); navigate("/settings?section=general"); }}>设置</MenuBtn>
          <MenuBtn onClick={() => { setOpen(false); navigate("/settings?section=models"); }}>模型配置</MenuBtn>
          <MenuBtn onClick={() => { setOpen(false); navigate("/billing"); }}>
            <CreditCard size={14} className="mr-2" />计费与用量
          </MenuBtn>
          <MenuBtn onClick={() => { setOpen(false); navigate("/audit"); }}>
            <ShieldCheck size={14} className="mr-2" />审计日志
          </MenuBtn>
        </div>
      )}
    </div>
  );
}

function MenuBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center rounded-lg px-3 py-2 text-left text-sm text-neutral-300 transition hover:bg-white/[0.06] hover:text-white"
    >
      {children}
    </button>
  );
}
