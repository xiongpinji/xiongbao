import { Link, NavLink } from "react-router-dom";
import { Bot, Grid2X2, Plus, Search, Settings } from "lucide-react";
import { useShellActions, useShellNavigation } from "../../shell/useShellStore";

export default function CollapsedRail() {
  const navigation = useShellNavigation();
  const { resetChatSession, setCommandPaletteOpen } = useShellActions();

  const chatItem = navigation.find((item) => item.taskId === "chat");
  const goalBoardItem = navigation.find((item) => item.taskId === "goal-board");
  const workflowItem = navigation.find((item) => item.taskId === "workflows");
  const agentsItem = navigation.find((item) => item.taskId === "agents");
  const settingsItem = navigation.find((item) => item.taskId === "settings");
  const primaryItems = [goalBoardItem, workflowItem, agentsItem, settingsItem].filter(
    (item): item is NonNullable<typeof item> => Boolean(item),
  );

  return (
    <aside className="flex h-screen w-14 shrink-0 flex-col items-center border-r border-white/[0.07] bg-black/48 py-3 text-neutral-300 backdrop-blur-2xl">
      <div className="xagent-brand-logo mb-5 h-9 w-9 rounded-xl">
        <img src="/assets/xiongbao-logo.png" alt="熊宝智能体系统" />
      </div>

      <nav className="flex w-full flex-col items-center gap-1 px-2">
        <Link
          to={chatItem?.preferredRoute ?? "/chat"}
          title="新建会话"
          onClick={resetChatSession}
          className={`flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
            chatItem?.active
              ? "bg-[#21180c] text-[#f2d99c] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
              : "text-neutral-500 hover:bg-white/[0.055] hover:text-white"
          }`}
        >
          <Plus size={18} strokeWidth={1.8} />
          <span className="sr-only">新建会话</span>
        </Link>
        <button
          type="button"
          title="搜索"
          onClick={() => setCommandPaletteOpen(true)}
          className="flex h-10 w-10 items-center justify-center rounded-xl text-neutral-500 transition-colors hover:bg-white/[0.055] hover:text-white"
        >
          <Search size={18} strokeWidth={1.8} />
          <span className="sr-only">搜索</span>
        </button>
      </nav>

      <div className="my-4 h-px w-8 bg-white/[0.07]" />

      <nav className="flex w-full flex-col items-center gap-1 px-2">
        {primaryItems.map((item) => (
          <RailLink key={item.taskId} to={item.preferredRoute} label={item.title} icon={resolveRailIcon(item.taskId)} active={item.active} />
        ))}
      </nav>
    </aside>
  );
}

function resolveRailIcon(taskId: string) {
  if (taskId === "agents") return Bot;
  if (taskId === "settings") return Settings;
  return Grid2X2;
}

function RailLink({
  to,
  label,
  icon: Icon,
  active,
}: {
  to: string;
  label: string;
  icon: typeof Plus;
  active: boolean;
}) {
  return (
    <NavLink
      to={to}
      title={label}
      className={() =>
        `flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
          active
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
