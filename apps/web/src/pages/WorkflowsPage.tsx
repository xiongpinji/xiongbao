import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import ReactFlow, {
  Background, Controls, MiniMap, ReactFlowProvider,
  useNodesState, useEdgesState, addEdge,
   type Connection, MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import { Plus, Play, Trash2 } from "lucide-react";
import { runWorkflow, type WorkflowView } from "../api";
import ConversationalCommand from "../components/chat/ConversationalCommand";
import { useShellActions } from "../shell/useShellStore";

interface Step { id: string; name: string; role?: string; goal: string; }

const workflowNodeStyle = {
  background: "#18181b",
  border: "1px solid #52525b",
  color: "#f4f4f5",
  borderRadius: 14,
  padding: 12,
  boxShadow: "0 18px 40px rgba(0,0,0,0.24)",
};

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const { syncRunTask } = useShellActions();
  const [name, setName] = useState("新工作流");
  const [view, setView] = useState<WorkflowView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState([
    { id: "s1", type: "input", position: { x: 100, y: 100 }, data: { label: "步骤1" }, style: workflowNodeStyle },
  ]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [steps, setSteps] = useState<Step[]>([{ id: "s1", name: "步骤1", goal: "" }]);

  const onConnect = useCallback((conn: Connection) => {
    setEdges(eds => addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed }, animated: true }, eds));
  }, [setEdges]);

  function addStep(goal = "") {
    const nextIndex = steps.length + 1;
    const id = `s${nextIndex}`;
    setSteps([...steps, { id, name: `步骤${nextIndex}`, goal }]);
    setNodes(ns => [...ns, {
      id, position: { x: 100 + steps.length * 200, y: 100 },
      data: { label: goal ? `步骤${nextIndex}: ${goal.slice(0, 12)}` : `步骤${nextIndex}` },
      style: workflowNodeStyle,
    }]);
  }

  function removeStep(id: string) {
    setSteps(ss => ss.filter(s => s.id !== id));
    setNodes(ns => ns.filter(n => n.id !== id));
    setEdges(es => es.filter(e => e.source !== id && e.target !== id));
  }

  async function run() {
    setLoading(true); setError(null);
    try {
      const valid = steps.filter(s => s.goal.trim());
      if (!valid.length) { setError("至少需要一个有目标的步骤"); return; }
      const nextView = await runWorkflow({ name, steps: valid });
      setView(nextView);
      syncRunTask(nextView.run_id, { source: "workflow" });
      navigate(`/runs/${encodeURIComponent(nextView.run_id)}`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }

  return (
    <ReactFlowProvider>
      <div className="flex h-full flex-col bg-transparent p-4 text-neutral-100 md:p-6">
        <div className="mb-4 flex flex-col gap-3 border-b border-white/[0.07] pb-4 md:flex-row md:items-center">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold text-white">工作流</h1>
            <p className="mt-1 text-xs text-neutral-500">在专业模式中维护步骤、依赖和执行结果。</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto] md:w-auto md:min-w-[520px]">
            <input className="field h-10 rounded-xl py-1.5" value={name}
              onChange={e => setName(e.target.value)} />
            <button onClick={() => addStep()} className="xagent-chip flex h-10 items-center justify-center gap-1 rounded-xl px-3">
              <Plus size={14} /> 添加步骤
            </button>
            <button onClick={run} disabled={loading}
              className="gold-button flex h-10 items-center justify-center gap-1 px-4">
              <Play size={14} /> {loading ? "执行中..." : "创建并执行"}
            </button>
          </div>
        </div>
        <ConversationalCommand
          compact
          className="mb-4"
          title="工作流编排助手"
          context="专业模式 / 工作流"
          placeholder="一句话描述要新增的步骤、审批或执行目标..."
          initialAssistantMessage="你说一句目标，我会把它写入工作流步骤，并同步到画布节点。"
          suggestions={["补一个质量验收步骤", "增加人工审批节点", "拆分成生成与校验两步"]}
          onSubmit={(value) => {
            addStep(value);
            return `已把「${value}」加入工作流步骤。你可以继续补充依赖关系，或直接创建并执行。`;
          }}
        />
        <div className="mb-3 max-h-40 space-y-2 overflow-auto">
          {steps.map(s => (
            <div key={s.id} className="grid gap-2 sm:grid-cols-[144px_minmax(0,1fr)_auto] sm:items-center">
              <input className="field h-9 rounded-xl py-1.5" placeholder="步骤名"
                value={s.name} onChange={e => setSteps(ss => ss.map(x => x.id === s.id ? { ...x, name: e.target.value } : x))} />
              <input className="field h-9 flex-1 rounded-xl py-1.5" placeholder="目标"
                value={s.goal} onChange={e => setSteps(ss => ss.map(x => x.id === s.id ? { ...x, goal: e.target.value } : x))} />
              <button onClick={() => removeStep(s.id)} className="flex h-9 items-center justify-center rounded-xl text-red-400 hover:bg-red-400/10 hover:text-red-300"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        {error && <div className="mb-3 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>}
        {view && (
          <div className="xagent-surface-subtle mb-3 p-3">
            <div className="mb-2 text-sm font-medium text-white">状态：<span className="text-blue-300">{view.status}</span></div>
            <div className="space-y-1">
              {view.steps.map(st => (
                <div key={st.id} className="flex items-center gap-2 text-sm text-neutral-300">
                  <span className="w-2 h-2 rounded-full" style={{ background: st.status === "succeeded" ? "#10b981" : st.status === "failed" ? "#ef4444" : "#f59e0b" }} />
                  <span>{st.name}</span><span className="text-xs text-neutral-500">({st.status})</span>
                  {st.has_approval && <span className="rounded bg-amber-400/10 px-1.5 text-xs text-amber-200">审批</span>}
                  {st.has_compensation && <span className="rounded bg-sky-400/10 px-1.5 text-xs text-sky-200">可补偿</span>}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="xagent-surface-subtle min-h-[320px] flex-1 overflow-hidden">
          <ReactFlow className="xagent-dark-flow" nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onConnect={onConnect} fitView minZoom={0.2} maxZoom={3}>
            <Background color="#3f3f46" gap={28} /><Controls /><MiniMap nodeColor="#52525b" maskColor="rgba(9,9,11,0.72)" />
          </ReactFlow>
        </div>
      </div>
    </ReactFlowProvider>
  );
}
