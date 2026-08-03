import { DRAMA_NODE_TYPES, type DramaNodeType } from "./canvasTypes";
import { nodeTypeColors } from "./canvasTheme";

export default function NodePalette({ onAddNode }: { onAddNode: (type: DramaNodeType) => void }) {
  return (
    <aside className="w-full shrink-0 border-b border-neutral-800 bg-neutral-900 p-4 text-neutral-200 lg:w-64 lg:border-b-0 lg:border-r">
      <div className="mb-4">
        <div className="text-sm font-semibold text-white">画布元素</div>
        <div className="mt-1 text-xs text-neutral-500">短剧流程节点</div>
      </div>
      <div className="space-y-1">
        {DRAMA_NODE_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => onAddNode(type)}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-neutral-300 transition hover:bg-neutral-800 hover:text-white"
          >
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: nodeTypeColors[type] }} />
            <span>{type}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
