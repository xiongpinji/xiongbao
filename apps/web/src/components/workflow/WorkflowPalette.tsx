/**
 * 工作流节点调色板 — 拖拽到画布
 */
import { WF_NODE_META, type WfNodeKind } from "./WorkflowNodes";
import { Bot, ShieldCheck, GitBranch, CircleDot, Flag } from "lucide-react";

const ICONS: Record<string, React.ReactNode> = {
  CircleDot: <CircleDot size={15} />,
  Bot: <Bot size={15} />,
  ShieldCheck: <ShieldCheck size={15} />,
  GitBranch: <GitBranch size={15} />,
  Flag: <Flag size={15} />,
};

const PALETTE_ORDER: WfNodeKind[] = ["start", "agent", "approval", "condition", "end"];

export default function WorkflowPalette({ onAddNode, onApplyTemplate }: { onAddNode: (kind: WfNodeKind) => void; onApplyTemplate: (name: string) => void }) {
  return (
    <div className="flex shrink-0 flex-col gap-1 border-b border-white/[0.06] bg-neutral-900/60 p-3 lg:w-52 lg:border-b-0 lg:border-r">
      <div className="mb-2 text-[11px] font-medium text-neutral-600">节点面板</div>
      {PALETTE_ORDER.map((kind) => {
        const meta = WF_NODE_META[kind];
        return (
          <button
            key={kind}
            type="button"
            draggable
            onDragStart={(e) => e.dataTransfer.setData("application/wf-node", kind)}
            onClick={() => onAddNode(kind)}
            className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] text-neutral-300 transition hover:bg-white/[0.06] hover:text-white active:scale-[0.97]"
          >
            <span style={{ color: meta.color }}>{ICONS[meta.icon]}</span>
            <span>{meta.label}</span>
          </button>
        );
      })}
      <div className="mt-3 border-t border-white/[0.06] pt-3">
        <div className="mb-2 text-[11px] font-medium text-neutral-600">快速模板</div>
        <button type="button" onClick={() => onApplyTemplate("sequential")}
          className="mb-1 w-full rounded-lg px-3 py-1.5 text-left text-[11px] text-neutral-400 transition hover:bg-white/[0.05] hover:text-white">
          + 顺序执行
        </button>
        <button type="button" onClick={() => onApplyTemplate("approval")}
          className="mb-1 w-full rounded-lg px-3 py-1.5 text-left text-[11px] text-neutral-400 transition hover:bg-white/[0.05] hover:text-white">
          + 审批链
        </button>
        <button type="button" onClick={() => onApplyTemplate("parallel")}
          className="w-full rounded-lg px-3 py-1.5 text-left text-[11px] text-neutral-400 transition hover:bg-white/[0.05] hover:text-white">
          + 并行分支
        </button>
      </div>
    </div>
  );
}
