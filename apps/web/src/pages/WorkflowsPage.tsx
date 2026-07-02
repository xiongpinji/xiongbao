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
import { useShellActions } from "../shell/useShellStore";

interface Step { id: string; name: string; role?: string; goal: string; }

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const { syncRunTask } = useShellActions();
  const [name, setName] = useState("demo");
  const [view, setView] = useState<WorkflowView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState([
    { id: "s1", type: "input", position: { x: 100, y: 100 }, data: { label: "步骤1: 打招呼" } },
  ]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [steps, setSteps] = useState<Step[]>([{ id: "s1", name: "打招呼", goal: "你好" }]);

  const onConnect = useCallback((conn: Connection) => {
    setEdges(eds => addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed }, animated: true }, eds));
  }, [setEdges]);

  function addStep() {
    const id = `s${steps.length + 1}`;
    setSteps([...steps, { id, name: `步骤${steps.length + 1}`, goal: "" }]);
    setNodes(ns => [...ns, {
      id, position: { x: 100 + steps.length * 200, y: 100 },
      data: { label: `步骤${steps.length + 1}` },
      style: { background: "#f0fdf4", border: "1px solid #86efac" },
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
      <div className="p-6 flex flex-col h-full">
        <div className="flex items-center gap-2 mb-4">
          <h1 className="text-xl font-semibold flex-1">工作流</h1>
          <input className="border rounded px-2 py-1 text-sm w-32" value={name}
            onChange={e => setName(e.target.value)} />
          <button onClick={addStep} className="px-3 py-1.5 bg-slate-700 text-white rounded text-sm flex items-center gap-1">
            <Plus size={14} /> 添加步骤
          </button>
          <button onClick={run} disabled={loading}
            className="px-4 py-1.5 bg-brand-600 text-white rounded text-sm flex items-center gap-1 disabled:opacity-50">
            <Play size={14} /> {loading ? "执行中..." : "创建并执行"}
          </button>
        </div>
        <div className="mb-3 space-y-2 max-h-40 overflow-auto">
          {steps.map(s => (
            <div key={s.id} className="flex gap-2 items-center">
              <input className="border rounded px-2 py-1 text-sm w-32" placeholder="步骤名"
                value={s.name} onChange={e => setSteps(ss => ss.map(x => x.id === s.id ? { ...x, name: e.target.value } : x))} />
              <input className="flex-1 border rounded px-2 py-1 text-sm" placeholder="目标"
                value={s.goal} onChange={e => setSteps(ss => ss.map(x => x.id === s.id ? { ...x, goal: e.target.value } : x))} />
              <button onClick={() => removeStep(s.id)} className="text-red-400 hover:text-red-600"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        {error && <div className="text-sm text-red-600 mb-3">{error}</div>}
        {view && (
          <div className="mb-3 bg-white border rounded-md p-3">
            <div className="text-sm font-medium mb-2">状态：<span className="text-brand-700">{view.status}</span></div>
            <div className="space-y-1">
              {view.steps.map(st => (
                <div key={st.id} className="text-sm flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: st.status === "succeeded" ? "#10b981" : st.status === "failed" ? "#ef4444" : "#f59e0b" }} />
                  <span>{st.name}</span><span className="text-xs text-slate-500">({st.status})</span>
                  {st.has_approval && <span className="text-xs bg-amber-100 text-amber-700 px-1.5 rounded">审批</span>}
                  {st.has_compensation && <span className="text-xs bg-blue-100 text-blue-700 px-1.5 rounded">可补偿</span>}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="flex-1 border rounded-md bg-white">
          <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onConnect={onConnect} fitView minZoom={0.2} maxZoom={3}>
            <Background /><Controls /><MiniMap />
          </ReactFlow>
        </div>
      </div>
    </ReactFlowProvider>
  );
}
