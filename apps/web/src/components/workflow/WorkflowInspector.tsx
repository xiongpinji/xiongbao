/**
 * 工作流节点检查器 — 配置选中节点的属性
 */
import { X } from "lucide-react";
import { WF_NODE_META, type WfNodeData, type WfNodeKind } from "./WorkflowNodes";

interface Props {
  node: { id: string; data: WfNodeData } | null;
  onChange: (id: string, patch: Partial<WfNodeData>) => void;
  onClose: () => void;
  onDelete: (id: string) => void;
}

function Field({ label, value, onChange, placeholder, textarea }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; textarea?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-neutral-500">{label}</span>
      {textarea ? (
        <textarea className="field min-h-[60px] w-full rounded-xl py-2 text-sm" value={value}
          onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={3} />
      ) : (
        <input className="field h-9 w-full rounded-xl py-1.5 text-sm" value={value}
          onChange={e => onChange(e.target.value)} placeholder={placeholder} />
      )}
    </label>
  );
}

export default function WorkflowInspector({ node, onChange, onClose, onDelete }: Props) {
  if (!node) return null;
  const { id, data } = node;
  const kind: WfNodeKind = data.kind;
  const meta = WF_NODE_META[kind];
  const set = (patch: Partial<WfNodeData>) => onChange(id, patch);

  return (
    <div className="absolute right-4 top-4 z-20 w-72 rounded-2xl border border-white/[0.08] bg-neutral-900/95 p-4 shadow-2xl backdrop-blur">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: meta.color }} />
          <span className="text-sm font-medium text-white">{meta.label}</span>
        </div>
        <button onClick={onClose} className="rounded-lg p-1 text-neutral-500 hover:bg-white/10 hover:text-white"><X size={14} /></button>
      </div>

      <div className="space-y-3">
        <Field label="名称" value={data.label} onChange={v => set({ label: v })} placeholder="节点名称" />

        {(kind === "agent") && (
          <>
            <Field label="角色 (Role)" value={data.role || ""} onChange={v => set({ role: v })} placeholder="general / coder / reviewer" />
            <Field label="目标 (Goal)" value={data.goal || ""} onChange={v => set({ goal: v })} placeholder="该步骤要完成的任务" textarea />
            <Field label="补偿动作" value={data.compensationGoal || ""} onChange={v => set({ compensationGoal: v })} placeholder="失败时的回滚操作（可选）" />
          </>
        )}

        {kind === "approval" && (
          <>
            <Field label="审批人角色" value={data.approverRole || ""} onChange={v => set({ approverRole: v })} placeholder="admin / reviewer" />
            <Field label="审批提示" value={data.approvalMessage || ""} onChange={v => set({ approvalMessage: v })} placeholder="审批时显示的消息" />
          </>
        )}

        {kind === "condition" && (
          <Field label="条件表达式" value={data.condition || ""} onChange={v => set({ condition: v })} placeholder="上一步结果包含 '成功'" />
        )}

        {kind !== "start" && kind !== "end" && (
          <button onClick={() => onDelete(id)}
            className="mt-2 w-full rounded-xl border border-red-500/30 py-2 text-xs text-red-400 transition hover:bg-red-500/10">
            删除节点
          </button>
        )}
      </div>
    </div>
  );
}
