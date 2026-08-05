import { GitBranch, History, Keyboard, Maximize2, Plus, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useEscapeClose } from "../../hooks/useEscapeClose";
import type { DramaNodeType } from "./canvasTypes";
import { DRAMA_NODE_TYPES } from "./canvasTypes";

const SHORTCUTS: { keys: string; desc: string }[] = [
  { keys: "⌘K / Ctrl+K", desc: "打开命令面板" },
  { keys: "Esc", desc: "关闭面板 / 停止生成" },
  { keys: "Enter", desc: "发送消息" },
  { keys: "Shift+Enter", desc: "换行" },
  { keys: "Delete", desc: "删除选中节点" },
  { keys: "滚轮", desc: "缩放画布" },
];

export default function CanvasToolbar({
  onAddNode,
  onFitView,
  onAutoLayout,
}: {
  onAddNode: (type: DramaNodeType) => void;
  onFitView: () => void;
  onAutoLayout?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const shortcutsRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // 点击浮层外部关闭（添加节点菜单 / 快捷键面板）
  useEffect(() => {
    if (!open && !showShortcuts) return;
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setShowShortcuts(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, showShortcuts]);

  // Esc 关闭浮层（键盘可达性）
  useEscapeClose(open || showShortcuts, () => {
    setOpen(false);
    setShowShortcuts(false);
  });

  function add(type: DramaNodeType) {
    onAddNode(type);
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="pointer-events-auto absolute bottom-5 left-1/2 z-20 -translate-x-1/2">
      {showShortcuts ? (
        <div ref={shortcutsRef} className="mb-3 w-72 rounded-lg border border-neutral-700 bg-neutral-900/95 p-3 shadow-2xl shadow-black/40 backdrop-blur">
          <div className="px-1 pb-2 text-xs font-medium text-neutral-500">键盘快捷键</div>
          <div className="space-y-1">
            {SHORTCUTS.map((s) => (
              <div key={s.keys} className="flex items-center justify-between rounded-md px-1.5 py-1 text-xs">
                <span className="text-neutral-400">{s.desc}</span>
                <kbd className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-neutral-300">{s.keys}</kbd>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {open ? (
        <div className="mb-3 w-80 rounded-lg border border-neutral-700 bg-neutral-900/95 p-2 text-sm text-neutral-200 shadow-2xl shadow-black/40 backdrop-blur" role="menu" aria-label="添加节点">
          <div className="px-3 pb-2 pt-2 text-xs font-medium text-neutral-500">添加节点</div>
          <div className="grid max-h-72 grid-cols-2 gap-1 overflow-auto">
            {DRAMA_NODE_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                role="menuitem"
                onClick={() => add(type)}
                className="rounded-lg px-3 py-2 text-left text-neutral-200 transition hover:bg-neutral-800 hover:text-white focus:outline-none focus:ring-2 focus:ring-neutral-500"
              >
                {type}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="flex items-center gap-2 rounded-lg border border-neutral-700 bg-neutral-900/95 p-2 text-neutral-300 shadow-2xl shadow-black/40 backdrop-blur">
        <button className="toolbar-button bg-neutral-100 text-neutral-950 hover:bg-white" onClick={() => setOpen((value) => !value)} title="添加节点" aria-label="添加节点">
          <Plus size={18} />
        </button>
        <button className="toolbar-button" title="连线模式（待实现）" aria-label="连线模式" disabled>
          <GitBranch size={18} />
        </button>
        <button className="toolbar-button" title="自动整理" aria-label="自动整理" onClick={onAutoLayout}>
          <Wand2 size={18} />
        </button>
        <button className="toolbar-button" onClick={onFitView} title="适应视图" aria-label="适应视图">
          <Maximize2 size={18} />
        </button>
        <button className="toolbar-button" title="历史（待实现）" aria-label="历史" disabled>
          <History size={18} />
        </button>
        <button
          className="toolbar-button"
          title="快捷键"
          aria-label="快捷键"
          onClick={() => { setShowShortcuts((v) => !v); setOpen(false); }}
        >
          <Keyboard size={18} />
        </button>
      </div>
    </div>
  );
}
