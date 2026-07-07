import { Bell, CircleHelp, Command, Edit3, Eye, FileText, Gem, Grid2X2, Wrench } from "lucide-react";

export default function TopBar() {
  const menuItems = [
    { label: "文件", icon: FileText },
    { label: "编辑", icon: Edit3 },
    { label: "视图", icon: Eye },
    { label: "帮助", icon: CircleHelp },
    { label: "工具", icon: Wrench },
  ];

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/[0.07] bg-black/56 px-5 text-neutral-300 backdrop-blur-2xl">
      <div className="text-sm font-semibold text-white md:hidden">X-Agent</div>
      <nav className="hidden min-w-0 flex-1 items-center gap-1 overflow-hidden md:flex">
        {menuItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              type="button"
              className="xagent-nav-item flex shrink-0 items-center gap-2 whitespace-nowrap px-2.5 py-1.5 text-sm"
            >
              <Icon size={15} className="text-neutral-600" strokeWidth={1.8} />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="flex shrink-0 items-center gap-2">
        <button className="xagent-chip hidden items-center gap-2 px-3 py-1.5 text-sm font-semibold sm:flex">
          <Gem size={15} className="text-violet-400" fill="currentColor" />
          Pro
        </button>
        <button className="xagent-chip relative hidden h-9 w-9 items-center justify-center p-0 sm:flex">
          <Bell size={16} />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[#d6ad62]" />
        </button>
        <button className="xagent-chip border-[#8a6a32]/35 bg-[#171108]/75 px-3 py-1.5 text-[#f2d99c]">
          就绪
        </button>
        <div className="hidden items-center gap-2 text-sm text-neutral-400 md:flex">
          <span>SESSION</span>
          <span className="font-mono text-neutral-200">
            {new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
        <button className="xagent-chip hidden h-8 w-8 items-center justify-center p-0 sm:flex">
          <Command size={16} />
        </button>
        <button className="xagent-chip flex h-8 w-8 items-center justify-center p-0">
          <Grid2X2 size={16} />
        </button>
      </div>
    </header>
  );
}
