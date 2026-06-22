import { ChevronDown, Folder, MoreHorizontal, TerminalSquare } from "lucide-react";

export default function TopBar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-800 bg-neutral-950/95 px-4 text-neutral-200">
      <div className="flex min-w-0 items-center gap-3">
        <div className="truncate text-sm font-semibold text-white">前端 UI 重构自由画布</div>
        <div className="flex items-center gap-2 rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-300">
          <Folder size={16} className="text-neutral-500" />
          <span>xiong bao</span>
          <ChevronDown size={14} className="text-neutral-500" />
        </div>
        <button className="rounded-lg p-1.5 text-neutral-500 hover:bg-neutral-900 hover:text-white" title="更多">
          <MoreHorizontal size={18} />
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button className="rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white">
          计划模式
        </button>
        <button className="flex items-center gap-2 rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white">
          <TerminalSquare size={15} /> 终端
        </button>
        <button className="rounded-xl bg-neutral-100 px-3 py-1.5 text-sm font-medium text-neutral-950 hover:bg-white">
          运行
        </button>
      </div>
    </header>
  );
}
