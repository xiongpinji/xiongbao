/**
 * 工作流自定义节点类型 + 调色板 + 检查器
 * 支持：Agent步骤 / 审批门 / 条件分支 / 开始 / 结束
 */
import { Handle, Position, type NodeProps } from "reactflow";
import { Bot, ShieldCheck, GitBranch, CircleDot, Flag } from "lucide-react";

// ─── 节点数据类型 ───
export type WfNodeKind = "start" | "agent" | "approval" | "condition" | "end";

export interface WfNodeData {
  kind: WfNodeKind;
  label: string;
  role?: string;
  goal?: string;
  approverRole?: string;
  approvalMessage?: string;
  compensationGoal?: string;
  condition?: string;
  [key: string]: unknown;
}

// ─── 节点元信息 ───
export const WF_NODE_META: Record<WfNodeKind, { label: string; color: string; icon: string }> = {
  start: { label: "开始", color: "#10b981", icon: "CircleDot" },
  agent: { label: "Agent 步骤", color: "#d6ad62", icon: "Bot" },
  approval: { label: "审批门", color: "#f59e0b", icon: "ShieldCheck" },
  condition: { label: "条件分支", color: "#8b5cf6", icon: "GitBranch" },
  end: { label: "结束", color: "#ef4444", icon: "Flag" },
};

const ICONS: Record<string, React.ReactNode> = {
  CircleDot: <CircleDot size={16} />,
  Bot: <Bot size={16} />,
  ShieldCheck: <ShieldCheck size={16} />,
  GitBranch: <GitBranch size={16} />,
  Flag: <Flag size={16} />,
};

// ─── 通用节点壳 ───
function NodeShell({ data, kind, children }: { data: WfNodeData; kind: WfNodeKind; children?: React.ReactNode }) {
  const meta = WF_NODE_META[kind];
  return (
    <div
      className="min-w-[160px] rounded-2xl border px-4 py-3 shadow-lg transition-shadow hover:shadow-xl"
      style={{ background: "#18181b", borderColor: `${meta.color}55` }}
    >
      {kind !== "start" && <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-2" style={{ background: meta.color }} />}
      <div className="flex items-center gap-2">
        <span style={{ color: meta.color }}>{ICONS[meta.icon]}</span>
        <span className="text-sm font-medium text-white">{data.label || meta.label}</span>
      </div>
      {children}
      {kind !== "end" && <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-2" style={{ background: meta.color }} />}
    </div>
  );
}

// ─── 各节点组件 ───
export function StartNode({ data }: NodeProps<WfNodeData>) {
  return <NodeShell data={data} kind="start" />;
}

export function AgentNode({ data }: NodeProps<WfNodeData>) {
  return (
    <NodeShell data={data} kind="agent">
      {data.role && <div className="mt-1.5 text-xs text-neutral-400">角色: {data.role}</div>}
      {data.goal && <div className="mt-1 max-w-[200px] truncate text-xs text-neutral-500">{data.goal}</div>}
    </NodeShell>
  );
}

export function ApprovalNode({ data }: NodeProps<WfNodeData>) {
  return (
    <NodeShell data={data} kind="approval">
      {data.approverRole && <div className="mt-1.5 text-xs text-amber-300/80">审批人: {data.approverRole}</div>}
    </NodeShell>
  );
}

export function ConditionNode({ data }: NodeProps<WfNodeData>) {
  return (
    <NodeShell data={data} kind="condition">
      {data.condition && <div className="mt-1.5 text-xs text-violet-300/80">条件: {data.condition}</div>}
      <Handle type="source" position={Position.Bottom} id="false" className="!h-2 !w-2" style={{ background: "#ef4444" }} />
    </NodeShell>
  );
}

export function EndNode({ data }: NodeProps<WfNodeData>) {
  return <NodeShell data={data} kind="end" />;
}

// ─── 注册到 ReactFlow ───
export const wfNodeTypes = {
  wfStart: StartNode,
  wfAgent: AgentNode,
  wfApproval: ApprovalNode,
  wfCondition: ConditionNode,
  wfEnd: EndNode,
};

export const kindToRfType: Record<WfNodeKind, string> = {
  start: "wfStart",
  agent: "wfAgent",
  approval: "wfApproval",
  condition: "wfCondition",
  end: "wfEnd",
};
