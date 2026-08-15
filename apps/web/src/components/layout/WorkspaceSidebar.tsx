import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  CalendarClock,
  CreditCard,
  GitPullRequest,
  Grid2X2,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  ShieldCheck,
  Target,
  Trash2,
  Wrench,
} from "lucide-react";
import { useShellActions, useShellStore } from "../../shell/useShellStore";
import { getToken } from "../../api/client";
import { buildApiUrl } from "../../api/baseUrl";
import { useConfirm } from "../../hooks/useConfirm";
import { useEscapeClose } from "../../hooks/useEscapeClose";

export default function WorkspaceSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { resetChatSession, setCommandPaletteOpen, setActiveConversationId } = useShellActions();
  const activeConversationId = useShellStore((s) => s.activeConversationId);

  if (collapsed) {
    return (
      <div className="xb-panel-left flex h-full w-[52px] shrink-0 flex-col items-center border-r border-white/[0.06] bg-[#111111] py-3">
        <button
          type="button"
          title="展开侧边栏"
          aria-label="展开侧边栏"
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
    <aside className="xb-panel-left flex h-full w-[240px] shrink-0 flex-col border-r border-white/[0.05] bg-[#0f0f0f]">
      {/* 顶部 logo + 折叠 */}
      <div className="flex items-center justify-between px-3 py-2.5">
        <div className="flex items-center gap-2 px-1">
          <div className="h-6 w-6 overflow-hidden rounded-md">
            <img src="/assets/xiongbao-logo.png" alt="X-Agent" className="h-full w-full object-cover" />
          </div>
          <span className="text-[13px] font-semibold text-neutral-100">X-Agent</span>
        </div>
        <button
          type="button"
          title="折叠侧边栏"
          aria-label="折叠侧边栏"
          onClick={onToggle}
          className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-600 transition hover:bg-white/[0.06] hover:text-neutral-300"
        >
          <PanelLeftClose size={15} />
        </button>
      </div>

      {/* 新建对话 */}
      <div className="px-2.5 pb-1.5 pt-1">
        <Link
          to="/chat"
          onClick={resetChatSession}
          className="flex w-full items-center gap-2 rounded-lg bg-white/[0.06] px-3 py-2 text-[13px] font-medium text-neutral-100 transition hover:bg-white/[0.1]"
        >
          <MessageSquarePlus size={15} className="text-neutral-400" />
          新建对话
        </Link>
      </div>

      {/* 搜索 */}
      <div className="px-2.5 pb-2">
        <button
          type="button"
          onClick={() => setCommandPaletteOpen(true)}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] text-neutral-600 transition hover:bg-white/[0.04] hover:text-neutral-400"
        >
          <Search size={13} />
          搜索
          <kbd className="ml-auto rounded bg-white/[0.05] px-1 py-0.5 text-[10px] text-neutral-700">⌘K</kbd>
        </button>
      </div>

      {/* 导航 */}
      <nav className="space-y-px border-b border-white/[0.04] px-2.5 pb-2.5">
        <NavItem to="/goal-board" icon={Target} label="目标看板" active={location.pathname === "/goal-board"} />
        <NavItem to="/professional?mode=workflow" icon={Grid2X2} label="工作流" active={location.pathname === "/professional"} />
        <NavItem to="/development-tasks" icon={GitPullRequest} label="开发任务" active={location.pathname === "/development-tasks"} />
        <NavItem to="/scheduler" icon={CalendarClock} label="调度中心" active={location.pathname === "/scheduler"} />
        <NavItem to="/agents" icon={Bot} label="智能体" active={location.pathname === "/agents"} />
        <NavItem to="/settings" icon={Wrench} label="设置" active={location.pathname === "/settings"} />
      </nav>

      {/* 会话历史 */}
      <div className="xagent-scrollbar min-h-0 flex-1 overflow-auto px-2.5 py-2.5">
        <div className="mb-1.5 px-1.5 text-[11px] font-medium text-neutral-600">
          最近对话
        </div>
        <ConversationList
          activeId={activeConversationId}
          onSelect={(id) => {
            setActiveConversationId(id);
            if (location.pathname !== "/chat") {
              navigate("/chat");
            }
          }}
        />
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
      className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition ${
        active
          ? "bg-white/[0.08] font-medium text-neutral-100"
          : "text-neutral-500 hover:bg-white/[0.04] hover:text-neutral-300"
      }`}
    >
      <Icon size={14} />
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

  // Esc 关闭用户菜单（键盘可达性）
  useEscapeClose(open, () => setOpen(false));

  return (
    <div ref={rootRef} className="relative border-t border-white/[0.05] p-2.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-white/[0.04]"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/[0.08] text-[11px] font-bold text-neutral-300">
          X
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-medium text-neutral-200">Xiongpinji</div>
          <div className="text-[10px] text-neutral-700">Pro</div>
        </div>
        <Settings size={13} className="shrink-0 text-neutral-700" />
      </button>

      {open && (
        <div className="absolute bottom-12 left-2.5 z-50 w-48 rounded-lg border border-white/[0.07] bg-[#1a1a1a] p-1 shadow-xl shadow-black/30">
          <MenuBtn onClick={() => { setOpen(false); navigate("/settings?section=general"); }}>设置</MenuBtn>
          <MenuBtn onClick={() => { setOpen(false); navigate("/settings?section=models"); }}>模型配置</MenuBtn>
          <MenuBtn onClick={() => { setOpen(false); navigate("/billing"); }}>
            <CreditCard size={13} className="mr-2" />计费用量
          </MenuBtn>
          <MenuBtn onClick={() => { setOpen(false); navigate("/audit"); }}>
            <ShieldCheck size={13} className="mr-2" />审计日志
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
      className="flex w-full items-center rounded-md px-2.5 py-1.5 text-left text-[12px] text-neutral-400 transition hover:bg-white/[0.05] hover:text-neutral-200"
    >
      {children}
    </button>
  );
}

/* ── 对话历史列表 ── */

interface ConvItem {
  conversation_id: string;
  title: string;
  last_active: number;
}

function ConversationList({ activeId, onSelect }: { activeId: string | null; onSelect: (id: string) => void }) {
  const [items, setItems] = useState<ConvItem[]>([]);
  const [loading, setLoading] = useState(true);
  const { confirm, ConfirmDialog } = useConfirm();

  const fetchList = useCallback(async () => {
    try {
      const token = getToken();
      const resp = await fetch(buildApiUrl("/api/v1/stream/conversations"), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) return;
      const data = await resp.json();
      setItems((data.conversations || []).slice(0, 20));
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    void fetchList();
    const timer = setInterval(() => void fetchList(), 15000);
    return () => clearInterval(timer);
  }, [fetchList]);

  // 当 activeId 变化时刷新（新对话创建后）
  useEffect(() => { void fetchList(); }, [activeId, fetchList]);

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    const ok = await confirm({ title: "删除对话", message: "确定删除该对话？历史记录将一并清除。", danger: true, confirmText: "删除" });
    if (!ok) return;
    const token = getToken();
    await fetch(buildApiUrl(`/api/v1/stream/conversations/${id}`), {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    setItems((prev) => prev.filter((c) => c.conversation_id !== id));
  }

  if (loading) {
    return <div className="px-3 py-4 text-center text-[11px] text-neutral-700">加载中...</div>;
  }

  if (items.length === 0) {
    return <div className="px-3 py-4 text-center text-[11px] text-neutral-700">暂无对话</div>;
  }

  return (
    <>
    <div className="space-y-px">
      {items.map((item) => (
        <div
          key={item.conversation_id}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(item.conversation_id)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(item.conversation_id); }}
          className={`group flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left transition ${
            activeId === item.conversation_id
              ? "bg-white/[0.07] text-neutral-200"
              : "text-neutral-500 hover:bg-white/[0.04] hover:text-neutral-300"
          }`}
        >
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12px] leading-4">{item.title}</div>
          </div>
          <button
            type="button"
            title="删除对话"
            onClick={(e) => { e.stopPropagation(); void handleDelete(e, item.conversation_id); }}
            className="shrink-0 rounded p-0.5 text-neutral-700 opacity-0 transition hover:text-red-400 group-hover:opacity-100"
          >
            <Trash2 size={10} />
          </button>
        </div>
      ))}
    </div>
    <ConfirmDialog />
    </>
  );
}
