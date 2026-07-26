import { Search, X } from "lucide-react";
import { useShellActions, useShellStore } from "../../shell/useShellStore";

const QUICK_ACTIONS = [
  "打开 Goal Board",
  "切换到工作流",
  "进入设置 / 技能",
  "返回对话",
];

export default function CommandPalette() {
  const open = useShellStore((state) => state.commandPaletteOpen);
  const { setCommandPaletteOpen } = useShellActions();

  if (!open) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex items-start justify-center bg-black/45 px-4 pt-20 backdrop-blur-sm">
      <div className="pointer-events-auto w-full max-w-xl rounded-3xl border border-white/[0.08] bg-[#111111]/96 shadow-[0_24px_80px_rgba(0,0,0,0.42)]">
        <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
          <div className="flex items-center gap-3 text-sm text-neutral-300">
            <Search size={16} className="text-[#d6ad62]" />
            <span className="font-medium text-white">搜索与命令面板</span>
          </div>
          <button
            type="button"
            title="关闭搜索"
            onClick={() => setCommandPaletteOpen(false)}
            className="rounded-xl p-2 text-neutral-500 transition hover:bg-white/[0.06] hover:text-white"
          >
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4">
          <div className="rounded-2xl border border-white/[0.08] bg-black/20 px-4 py-3 text-sm text-neutral-500">
            输入搜索词或选择一个快捷入口。当前为最小可用 command palette。
          </div>
          <div className="mt-4 space-y-2">
            {QUICK_ACTIONS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setCommandPaletteOpen(false)}
                className="flex w-full items-center justify-between rounded-2xl border border-white/[0.05] bg-white/[0.02] px-4 py-3 text-left text-sm text-neutral-200 transition hover:border-white/[0.09] hover:bg-white/[0.05] hover:text-white"
              >
                <span>{item}</span>
                <span className="text-xs text-neutral-500">Enter</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
