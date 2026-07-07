import { NavLink } from "react-router-dom";
import { Bot, Code2, MessageSquare, Plus, Sparkles } from "lucide-react";

const primaryItems = [
  { to: "/chat", label: "新建任务", icon: Plus },
  { to: "/settings?section=skills", label: "技能", icon: Sparkles },
  { to: "/creative/canvas", label: "专业模式", icon: Code2 },
];

const workspaceItems = [
  { to: "/chat", label: "对话", icon: MessageSquare },
  { to: "/agents", label: "智能体", icon: Bot },
];

export default function CollapsedRail() {
  return (
    <aside className="flex h-screen w-14 shrink-0 flex-col items-center border-r border-white/[0.07] bg-black/48 py-3 text-neutral-300 backdrop-blur-2xl">
      <div className="xagent-brand-logo mb-5 h-9 w-9 rounded-xl">
        <img src="/assets/xiongbao-logo.png" alt="熊宝智能体系统" />
      </div>

      <nav className="flex w-full flex-col items-center gap-1 px-2">
        {primaryItems.map((item) => (
          <RailLink key={item.label} {...item} />
        ))}
      </nav>

      <div className="my-4 h-px w-8 bg-white/[0.07]" />

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
            ? "bg-[#21180c] text-[#f2d99c] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
            : "text-neutral-500 hover:bg-white/[0.055] hover:text-white"
        }`
      }
    >
      <Icon size={18} strokeWidth={1.8} />
      <span className="sr-only">{label}</span>
    </NavLink>
  );
}
