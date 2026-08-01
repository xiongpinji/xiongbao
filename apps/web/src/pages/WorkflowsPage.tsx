/**
 * 工作流可视化编排页面 — 拖拽式编辑器
 * 支持：自定义节点 / 拖拽添加 / 连线=依赖 / 节点配置 / 模板 / 执行
 */
import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import ReactFlow, {
  Background, Controls, MiniMap, ReactFlowProvider,
  useNodesState, useEdgesState, addEdge, useReactFlow,
  type Connection, type Node, type Edge, MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import { Play, Save, Trash2 } from "lucide-react";
import { runWorkflow, type WorkflowView } from "../api";
import { api } from "../api/client";
import { useShellActions } from "../shell/useShellStore";
import { wfNodeTypes, kindToRfType, WF_NODE_META, type WfNodeData, type WfNodeKind } from "../components/workflow/WorkflowNodes";
import WorkflowPalette from "../components/workflow/WorkflowPalette";
import WorkflowInspector from "../components/workflow/WorkflowInspector";

let _nodeSeq = 10;
function nextId() { return `wf_${++_nodeSeq}`; }

const edgeStyle = { stroke: "#52525b", strokeWidth: 1.5 };
const defaultEdge = { markerEnd: { type: MarkerType.ArrowClosed, color: "#d6ad62" }, animated: true, style: edgeStyle };

// ─── 模板 ───
const TEMPLATES: Record<string, { nodes: { kind: WfNodeKind; label: string }[] }> = {
  sequential: {
    nodes: [
      { kind: "start", label: "开始" },
      { kind: "agent", label: "步骤1" },
      { kind: "agent", label: "步骤2" },
      { kind: "end", label: "结束" },
    ],
  },
  approval: {
    nodes: [
      { kind: "start", label: "开始" },
      { kind: "agent", label: "执行" },
      { kind: "approval", label: "审批" },
      { kind: "end", label: "结束" },
    ],
  },
  parallel: {
    nodes: [
      { kind: "start", label: "开始" },
      { kind: "agent", label: "分支A" },
      { kind: "agent", label: "分支B" },
      { kind: "condition", label: "汇总判断" },
      { kind: "end", label: "结束" },
    ],
  },
};

function buildTemplateNodes(name: string): { nodes: Node<WfNodeData>[]; edges: Edge[] } {
  const tpl = TEMPLATES[name];
  if (!tpl) return { nodes: [], edges: [] };
  const nodes: Node<WfNodeData>[] = tpl.nodes.map((n, i) => ({
    id: nextId(),
    type: kindToRfType[n.kind],
    position: { x: 80 + i * 220, y: 120 + (i % 2 === 0 ? 0 : 60) },
    data: { kind: n.kind, label: n.label },
  }));
  const edges: Edge[] = nodes.slice(1).map((n, i) => ({
    id: `e_${nodes[i].id}_${n.id}`,
    source: nodes[i].id,
    target: n.id,
    ...defaultEdge,
  }));
  return { nodes, edges };
}

// ─── 初始画布 ───
const INIT_NODES: Node<WfNodeData>[] = [
  { id: "wf_start", type: "wfStart", position: { x: 60, y: 150 }, data: { kind: "start", label: "开始" } },
  { id: "wf_end", type: "wfEnd", position: { x: 600, y: 150 }, data: { kind: "end", label: "结束" } },
];

export default function WorkflowsPage() {
  return (
    <ReactFlowProvider>
      <WorkflowsInner />
    </ReactFlowProvider>
  );
}

function WorkflowsInner() {
  const navigate = useNavigate();
  const { syncRunTask } = useShellActions();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();

  const [name, setName] = useState("新工作流");
  const [nodes, setNodes, onNodesChange] = useNodesState<WfNodeData>(INIT_NODES);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<{ id: string; data: WfNodeData } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastView, setLastView] = useState<WorkflowView | null>(null);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [savedTemplates, setSavedTemplates] = useState<{ template_id: string; name: string; version: number }[]>([]);

  const onConnect = useCallback((conn: Connection) => {
    setEdges(eds => addEdge({ ...conn, ...defaultEdge }, eds));
  }, [setEdges]);

  // ─── 添加节点 ───
  const addNode = useCallback((kind: WfNodeKind, pos?: { x: number; y: number }) => {
    const id = nextId();
    const meta = WF_NODE_META[kind];
    const position = pos || { x: 200 + Math.random() * 200, y: 100 + Math.random() * 150 };
    const newNode: Node<WfNodeData> = {
      id,
      type: kindToRfType[kind],
      position,
      data: { kind, label: meta.label },
    };
    setNodes(ns => [...ns, newNode]);
  }, [setNodes]);

  // ─── 拖放 ───
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const kind = e.dataTransfer.getData("application/wf-node") as WfNodeKind;
    if (!kind) return;
    const pos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    addNode(kind, pos);
  }, [screenToFlowPosition, addNode]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  // ─── 节点选中 ───
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node<WfNodeData>) => {
    setSelectedNode({ id: node.id, data: node.data });
  }, []);

  // ─── 节点属性更新 ───
  const updateNodeData = useCallback((id: string, patch: Partial<WfNodeData>) => {
    setNodes(ns => ns.map(n => n.id === id ? { ...n, data: { ...n.data, ...patch } } : n));
    setSelectedNode(prev => prev && prev.id === id ? { ...prev, data: { ...prev.data, ...patch } } : prev);
  }, [setNodes]);

  const deleteNode = useCallback((id: string) => {
    setNodes(ns => ns.filter(n => n.id !== id));
    setEdges(es => es.filter(e => e.source !== id && e.target !== id));
    setSelectedNode(null);
  }, [setNodes, setEdges]);

  // ─── 应用模板 ───
  function applyTemplate(tplName: string) {
    const { nodes: tn, edges: te } = buildTemplateNodes(tplName);
    if (tn.length) { setNodes(tn); setEdges(te); setSelectedNode(null); }
  }

  // ─── 保存/加载模板 ───
  const refreshTemplates = useCallback(async () => {
    try {
      const resp = await api.get("/workflows/templates/list");
      setSavedTemplates(resp.data.templates.map((t: { template_id: string; name: string; version: number }) => ({ template_id: t.template_id, name: t.name, version: t.version })));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { refreshTemplates(); }, [refreshTemplates]);

  async function saveTemplate() {
    try {
      const resp = await api.post("/workflows/templates/save", {
        name, nodes: nodes.map(n => ({ id: n.id, type: n.type, position: n.position, data: n.data })),
        edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target })),
        template_id: templateId,
      });
      setTemplateId(resp.data.template.template_id);
      setError(null);
      refreshTemplates();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "保存失败"); }
  }

  async function loadTemplate(tid: string) {
    try {
      const resp = await api.get(`/workflows/templates/${tid}`);
      const tpl = resp.data.template;
      setName(tpl.name);
      setTemplateId(tpl.template_id);
      setNodes(tpl.nodes);
      setEdges(tpl.edges.map((e: { id: string; source: string; target: string }) => ({ ...e, ...defaultEdge })));
      setSelectedNode(null);
      setError(null);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "加载失败"); }
  }

  async function deleteTemplate(tid: string) {
    try {
      await api.delete(`/workflows/templates/${tid}`);
      if (templateId === tid) setTemplateId(null);
      refreshTemplates();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "删除失败"); }
  }

  // ─── 从画布提取步骤 → 提交后端 ───
  function extractSteps() {
    // 构建依赖图：edge.source → edge.target 意味着 target depends_on source
    const depMap: Record<string, string[]> = {};
    edges.forEach(e => {
      if (!depMap[e.target]) depMap[e.target] = [];
      depMap[e.target].push(e.source);
    });
    return nodes
      .filter(n => n.data.kind === "agent" || n.data.kind === "approval")
      .map(n => ({
        id: n.id,
        name: n.data.label || n.id,
        role: n.data.role || "general",
        goal: n.data.goal || n.data.label || "",
        depends_on: (depMap[n.id] || []).filter(d => nodes.find(x => x.id === d)?.data.kind !== "start"),
        approver_role: n.data.kind === "approval" ? (n.data.approverRole || "admin") : undefined,
        approval_message: n.data.kind === "approval" ? (n.data.approvalMessage || "") : undefined,
        compensation_goal: n.data.compensationGoal || undefined,
      }));
  }

  async function run() {
    setLoading(true); setError(null);
    try {
      const steps = extractSteps();
      if (!steps.length) { setError("画布中至少需要一个 Agent 步骤或审批门"); return; }
      const view = await runWorkflow({ name, steps });
      setLastView(view);
      syncRunTask(view.run_id, { source: "workflow" });
      navigate(`/runs/${encodeURIComponent(view.run_id)}`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }

  return (
    <div className="flex h-full flex-col bg-transparent text-neutral-100">
        {/* 顶栏 */}
        <div className="flex items-center gap-3 border-b border-white/[0.07] px-4 py-3 md:px-6">
          <h1 className="text-lg font-semibold text-white">工作流编排</h1>
          <input className="field h-9 w-48 rounded-xl py-1.5 text-sm" value={name}
            onChange={e => setName(e.target.value)} placeholder="工作流名称" />
          <div className="ml-auto flex items-center gap-2">
            {savedTemplates.length > 0 && (
              <select className="field h-9 rounded-xl px-3 text-sm" defaultValue=""
                onChange={e => { if (e.target.value) loadTemplate(e.target.value); e.target.value = ""; }}>
                <option value="" disabled>打开...</option>
                {savedTemplates.map(t => <option key={t.template_id} value={t.template_id}>{t.name} (v{t.version})</option>)}
              </select>
            )}
            <button onClick={saveTemplate}
              className="flex h-9 items-center gap-1.5 rounded-xl border border-white/10 px-3 text-sm text-neutral-300 transition hover:border-[#d6ad62]/40 hover:text-[#d6ad62]">
              <Save size={14} /> 保存
            </button>
            {templateId && (
              <button onClick={() => deleteTemplate(templateId)}
                className="flex h-9 items-center gap-1.5 rounded-xl border border-white/10 px-3 text-sm text-neutral-400 transition hover:border-red-500/40 hover:text-red-400">
                <Trash2 size={14} />
              </button>
            )}
            <select className="field h-9 rounded-xl px-3 text-sm" defaultValue=""
              onChange={e => { if (e.target.value) applyTemplate(e.target.value); e.target.value = ""; }}>
              <option value="" disabled>模板...</option>
              <option value="sequential">顺序执行</option>
              <option value="approval">审批链</option>
              <option value="parallel">并行分支</option>
            </select>
            <button onClick={run} disabled={loading}
              className="gold-button flex h-9 items-center gap-1.5 rounded-xl px-4 text-sm">
              <Play size={14} /> {loading ? "执行中..." : "执行"}
            </button>
          </div>
        </div>

        {error && <div className="mx-4 mt-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>}

        {/* 主体：调色板 + 画布 */}
        <div className="flex min-h-0 flex-1">
          <WorkflowPalette onAddNode={(kind) => addNode(kind)} />
          <div className="relative min-w-0 flex-1" ref={reactFlowWrapper} onDrop={onDrop} onDragOver={onDragOver}>
            <ReactFlow
              nodes={nodes} edges={edges}
              nodeTypes={wfNodeTypes}
              onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
              onConnect={onConnect} onNodeClick={onNodeClick}
              onPaneClick={() => setSelectedNode(null)}
              fitView minZoom={0.2} maxZoom={3}
              deleteKeyCode={["Backspace", "Delete"]}
              className="xagent-dark-flow"
            >
              <Background color="#3f3f46" gap={28} />
              <Controls />
              <MiniMap nodeColor="#52525b" maskColor="rgba(9,9,11,0.72)" />
            </ReactFlow>
            <WorkflowInspector
              node={selectedNode}
              onChange={updateNodeData}
              onClose={() => setSelectedNode(null)}
              onDelete={deleteNode}
            />
          </div>
        </div>

        {/* 底部状态 */}
        {lastView && (
          <div className="border-t border-white/[0.07] px-4 py-2 text-xs text-neutral-500">
            上次执行: <span className="text-blue-300">{lastView.status}</span> · {lastView.steps.length} 步骤 · run_id: {lastView.run_id.slice(0, 8)}
          </div>
        )}
      </div>
  );
}
