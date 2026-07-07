import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bot, Code2, MessageSquarePlus, PanelLeftClose, PanelLeftOpen, Search, Settings, SlidersHorizontal } from "lucide-react";

const sessions = [
  {
    name: "对话",
    subtitle: "统一工作区主对话",
    status: "待开始",
    time: "4 分钟前",
    route: "/chat",
  },
  {
    name: "短剧工厂",
    subtitle: "剧本、分镜、生成与剪辑",
    status: "就绪",
    time: "8 分钟前",
    route: "/creative/canvas",
  },
  {
    name: "工作流",
    subtitle: "编排任务、审批与执行",
    status: "就绪",
    time: "12 分钟前",
    route: "/professional?mode=workflow",
  },
  {
    name: "智能体",
    subtitle: "角色与能力配置",
    status: "待配置",
    time: "18 分钟前",
    route: "/agents",
  },
];

const settingsShortcuts = [
  { label: "常规", section: "general" },
  { label: "模型设置", section: "models" },
  { label: "技能", section: "skills" },
  { label: "索引库", section: "index" },
  { label: "使用统计", section: "usage" },
];

export default function WorkspaceSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
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
          className="gold-button flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left"
        >
          <span className="flex items-center gap-2"><MessageSquarePlus size={16} />新建会话</span>
          <span className="rounded-md bg-black/20 px-2 py-0.5 text-xs text-[#fff0bf]">Ctrl+N</span>
        </Link>
        <button className="xagent-nav-item flex w-full items-center justify-between px-3 py-2 text-left text-sm">
          <span className="flex items-center gap-2"><Search size={15} />搜索</span>
          <span className="text-xs text-neutral-600">Ctrl+K</span>
        </button>
        <Link
          to="/creative/canvas"
          className="xagent-nav-item flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
        >
          <Code2 size={15} />专业模式
        </Link>
        <Link
          to="/settings?section=skills"
          className="xagent-nav-item flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
        >
          <SlidersHorizontal size={15} />技能
        </Link>
        <Link
          to="/agents"
          className="xagent-nav-item flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
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
          {sessions.map((project, index) => (
            <Link
              key={project.name}
              to={project.route}
              className={`block border-b border-white/[0.055] px-4 py-3 text-sm transition last:border-b-0 hover:bg-white/[0.045] ${
                index === 0 ? "bg-white/[0.055] text-white" : "text-neutral-300"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="truncate font-medium">{project.name}</div>
                <span className="shrink-0 text-xs text-neutral-500">{project.time}</span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-3 text-xs">
                <span className="truncate text-neutral-600">{project.subtitle}</span>
                <span className="shrink-0 text-[#d6ad62]">{project.status}</span>
              </div>
            </Link>
          ))}
        </div>
        <div className="mt-4 rounded-2xl border border-dashed border-white/[0.08] bg-black/18 p-4 text-sm leading-6 text-neutral-500">
          会话中产生任务后，右侧 Context 会自动同步文件、运行和产物看板。
        </div>
      </div>

      <UserRow />
    </aside>
  );
}

function UserRow() {
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
            to="/settings"
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
