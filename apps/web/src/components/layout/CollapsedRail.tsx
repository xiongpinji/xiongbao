import { NavLink } from "react-router-dom";
import { Bot, Film, MessageSquare, Plus, Search, Sparkles, Workflow } from "lucide-react";

const primaryItems = [
  { to: "/chat", label: "新建任务", icon: Plus },
  { to: "/chat", label: "搜索", icon: Search },
  { to: "/settings?section=skills", label: "技能", icon: Sparkles },
  { to: "/creative", label: "短剧工厂", icon: Film },
  { to: "/workflows", label: "工作流", icon: Workflow },
];

const workspaceItems = [
  { to: "/chat", label: "对话", icon: MessageSquare },
  { to: "/agents", label: "智能体", icon: Bot },
];

export default function CollapsedRail() {
  return (
    <aside className="flex h-screen w-14 shrink-0 flex-col items-center border-r border-neutral-800 bg-neutral-950 py-3 text-neutral-300">
      <div className="mb-5 flex h-9 w-9 items-center justify-center rounded-xl border border-neutral-700 bg-neutral-900 text-lg font-black text-white shadow-sm">
        X
      </div>

      <nav className="flex w-full flex-col items-center gap-1 px-2">
        {primaryItems.map((item) => (
          <RailLink key={item.label} {...item} />
        ))}
      </nav>

      <div className="my-4 h-px w-8 bg-neutral-800" />

      <nav className="flex w-full flex-1 flex-col items-center gap-1 px-2">
        {workspaceItems.map((item) => (
          <RailLink key={item.label} {...item} />
        ))}
      </nav>
    </aside>
  );
}

function RailLink({ to, label, icon: Icon }: { to: string; label: string; icon: typeof Plus }) {
  return (
    <NavLink
      to={to}
      title={label}
      className={({ isActive }) =>
        `flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
          isActive
            ? "bg-neutral-800 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
            : "text-neutral-400 hover:bg-neutral-900 hover:text-white"
        }`
      }
    >
      <Icon size={18} strokeWidth={1.8} />
      <span className="sr-only">{label}</span>
    </NavLink>
  );
}
