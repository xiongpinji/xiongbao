import { GitBranch, History, Keyboard, Maximize2, Plus, Wand2 } from "lucide-react";
import { useState } from "react";
import type { DramaNodeType } from "./canvasTypes";
import { DRAMA_NODE_TYPES } from "./canvasTypes";

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

  function add(type: DramaNodeType) {
    onAddNode(type);
    setOpen(false);
  }

  return (
    <div className="pointer-events-auto absolute bottom-5 left-1/2 z-20 -translate-x-1/2">
      {open ? (
        <div className="mb-3 w-80 rounded-3xl border border-neutral-700 bg-neutral-900/95 p-2 text-sm text-neutral-200 shadow-2xl shadow-black/40 backdrop-blur" role="menu" aria-label="添加节点">
          <div className="px-3 pb-2 pt-2 text-xs font-medium text-neutral-500">添加节点</div>
          <div className="grid max-h-72 grid-cols-2 gap-1 overflow-auto">
            {DRAMA_NODE_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                role="menuitem"
                onClick={() => add(type)}
                className="rounded-2xl px-3 py-2 text-left text-neutral-200 transition hover:bg-neutral-800 hover:text-white focus:outline-none focus:ring-2 focus:ring-neutral-500"
              >
                {type}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="flex items-center gap-2 rounded-3xl border border-neutral-700 bg-neutral-900/95 p-2 text-neutral-300 shadow-2xl shadow-black/40 backdrop-blur">
        <button className="toolbar-button bg-neutral-100 text-neutral-950 hover:bg-white" onClick={() => setOpen((value) => !value)} title="添加节点" aria-label="添加节点">
          <Plus size={18} />
        </button>
        <button className="toolbar-button" title="连线模式" aria-label="连线模式">
          <GitBranch size={18} />
        </button>
        <button className="toolbar-button" title="自动整理" aria-label="自动整理" onClick={onAutoLayout}>
          <Wand2 size={18} />
        </button>
        <button className="toolbar-button" onClick={onFitView} title="适应视图" aria-label="适应视图">
          <Maximize2 size={18} />
        </button>
        <button className="toolbar-button" title="历史" aria-label="历史">
          <History size={18} />
        </button>
        <button className="toolbar-button" title="快捷键" aria-label="快捷键">
          <Keyboard size={18} />
        </button>
      </div>
    </div>
  );
}
