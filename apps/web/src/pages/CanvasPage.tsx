import { useState, useCallback } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  addEdge,
  type Node,
  type Connection,
  type NodeTypes,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import { Send, Check, X, MessageSquare, Image, Video, Clapperboard } from "lucide-react";
import { callMcpTool } from "../api";

const NODE_COLORS: Record<string, string> = {
  "需求分析": "#3b82f6",
  "梗概": "#8b5cf6",
  "角色设定": "#ec4899",
  "分镜": "#f59e0b",
  "关键帧": "#10b981",
  "视频": "#06b6d4",
  "配音": "#6366f1",
  "字幕": "#f97316",
  "配乐": "#14b8a6",
  "导出": "#ef4444",
};

interface CanvasNode {
  node_id: string; node_type: string; title: string; content: any;
  status: string; agent_note: string; human_note: string; position: {x: number; y: number};
  dependencies: string[];
}

interface CanvasData { canvas_id: string; title: string; brief: string; nodes: CanvasNode[]; }

function NodeReviewPanel({ node, onReview, onClose, onGenerate }: {
  node: CanvasNode;
  onReview: (status: string, note: string, content?: any) => void;
  onClose: () => void;
  onGenerate: (kind: "image" | "video", prompt: string) => void;
}) {
  const [note, setNote] = useState(node.human_note || "");
  const [content, setContent] = useState(
    typeof node.content === "string" ? node.content : JSON.stringify(node.content || "", null, 2)
  );
  const isImageNode = node.node_type === "关键帧";
  const isVideoNode = node.node_type === "视频";
  const promptText = typeof node.content === "string" ? node.content : node.title;

  return (
    <div className="border rounded-md bg-white shadow-lg p-4 w-80 space-y-3">
      <div className="flex justify-between items-center">
        <span className="font-medium text-sm">{node.node_type}</span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={16} /></button>
      </div>
      <div className="text-xs text-slate-500">{node.title}</div>
      {node.agent_note && <div className="text-xs text-blue-600 bg-blue-50 p-2 rounded">AI {node.agent_note}</div>}
      <textarea className="w-full border rounded text-xs p-2 h-16" placeholder="内容" value={content}
        onChange={e => setContent(e.target.value)} />
      <textarea className="w-full border rounded text-xs p-2 h-16" placeholder="修改意见" value={note}
        onChange={e => setNote(e.target.value)} />
      <div className="text-xs text-slate-400">当前状态: {node.status}</div>
      {/* 媒体生成按钮 */}
      {(isImageNode || isVideoNode) && (
        <div className="flex gap-2">
          {isImageNode && (
            <button onClick={() => onGenerate("image", promptText)}
              className="flex-1 px-2 py-1.5 bg-emerald-600 text-white rounded text-xs flex items-center justify-center gap-1">
              <Image size={12} /> 出图
            </button>
          )}
          {isVideoNode && (
            <button onClick={() => onGenerate("video", promptText)}
              className="flex-1 px-2 py-1.5 bg-cyan-600 text-white rounded text-xs flex items-center justify-center gap-1">
              <Video size={12} /> 出视频
            </button>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <button onClick={() => onReview("approved", note)}
          className="flex-1 px-2 py-1.5 bg-green-600 text-white rounded text-xs flex items-center justify-center gap-1">
          <Check size={12} /> 通过
        </button>
        <button onClick={() => onReview("rejected", note)}
          className="flex-1 px-2 py-1.5 bg-red-600 text-white rounded text-xs flex items-center justify-center gap-1">
          <X size={12} /> 驳回
        </button>
        <button onClick={() => onReview("modified", note, content)}
          className="flex-1 px-2 py-1.5 bg-amber-600 text-white rounded text-xs flex items-center justify-center gap-1">
          <MessageSquare size={12} /> 修改
        </button>
      </div>
    </div>
  );
}

function CanvasNodeWidget({ data }: { data: any }) {
  const color = NODE_COLORS[data.node_type] || "#94a3b8";
  const statusColor = data.status === "approved" ? "bg-green-100 text-green-700"
    : data.status === "rejected" ? "bg-red-100 text-red-700"
    : data.status === "modified" ? "bg-amber-100 text-amber-700"
    : "bg-slate-100 text-slate-500";

  return (
    <div className="border-2 rounded-lg bg-white shadow-sm p-3 w-56" style={{ borderColor: color }}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium" style={{ color }}>{data.node_type}</span>
        {data.status !== "pending" && (
          <span className={`text-xs px-1.5 py-0.5 rounded ${statusColor}`}>{data.status}</span>
        )}
      </div>
      <div className="text-sm font-medium truncate">{data.title}</div>
      {data.human_note && <div className="text-xs text-amber-600 mt-1 line-clamp-2">备注 {data.human_note}</div>}
      {data.agent_note && !data.human_note && (
        <div className="text-xs text-blue-500 mt-1 line-clamp-2">AI {data.agent_note}</div>
      )}
    </div>
  );
}

const nodeTypes: NodeTypes = { canvasNode: CanvasNodeWidget };

// ─── 短剧导入面板 ───
interface DramaItem { id: number; title: string; genre: string; total_episodes: number; status: string; }

function DramaImportPanel({ onImport, onClose }: {
  onImport: (drama: any) => void;
  onClose: () => void;
}) {
  const [dramas, setDramas] = useState<DramaItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadDramas() {
    setLoading(true); setError(null);
    try {
      const res: any = await callMcpTool("huobao-drama", "list_dramas", {});
      const text = res?.content?.[0]?.text || res?.result || JSON.stringify(res);
      const parsed = typeof text === "string" ? JSON.parse(text) : text;
      setDramas(parsed?.data?.items || []);
    } catch (e: any) { setError(e.message || "加载失败"); }
    finally { setLoading(false); }
  }

  async function importDrama(d: DramaItem) {
    setLoading(true);
    try {
      const res: any = await callMcpTool("huobao-drama", "get_drama", { drama_id: d.id });
      const text = res?.content?.[0]?.text || res?.result || JSON.stringify(res);
      const parsed = typeof text === "string" ? JSON.parse(text) : text;
      onImport(parsed?.data || parsed);
    } catch (e: any) { setError(e.message || "导入失败"); }
    finally { setLoading(false); }
  }

  return (
    <div className="absolute left-4 top-4 z-20 w-72 rounded-xl border border-neutral-700 bg-neutral-900/95 p-4 shadow-2xl backdrop-blur">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-white flex items-center gap-2"><Clapperboard size={16} className="text-[#d6ad62]" /> 短剧平台</span>
        <button onClick={onClose} className="text-neutral-500 hover:text-white"><X size={16} /></button>
      </div>
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {dramas.length === 0 ? (
        <button onClick={loadDramas} disabled={loading}
          className="w-full rounded-lg bg-[#d6ad62]/15 px-3 py-2 text-sm text-[#d6ad62] hover:bg-[#d6ad62]/25 disabled:opacity-50">
          {loading ? "加载中..." : "加载短剧列表"}
        </button>
      ) : (
        <div className="space-y-2 max-h-64 overflow-auto">
          {dramas.map(d => (
            <button key={d.id} onClick={() => importDrama(d)} disabled={loading}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-800 p-3 text-left hover:border-[#d6ad62]/50 transition disabled:opacity-50">
              <div className="text-sm text-white font-medium">{d.title}</div>
              <div className="text-xs text-neutral-500 mt-1">{d.genre} · {d.total_episodes}集 · {d.status}</div>
            </button>
          ))}
          <button onClick={loadDramas} className="w-full text-xs text-neutral-500 hover:text-neutral-300 py-1">刷新</button>
        </div>
      )}
    </div>
  );
}

export default function CanvasPage() {
  const [brief, setBrief] = useState("");
  const [canvas, setCanvas] = useState<CanvasData | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<CanvasNode | null>(null);
  const [showDramaPanel, setShowDramaPanel] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const onConnect = useCallback((conn: Connection) => {
    setEdges(eds => addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed } }, eds));
  }, [setEdges]);

  // 将短剧数据转为画布节点
  function importDramaToCanvas(drama: any) {
    const imported: CanvasNode[] = [];
    let x = 80, y = 80;
    // 短剧根节点
    imported.push({ node_id: `drama-${drama.id}`, node_type: "梗概", title: drama.title || "短剧", content: drama.description || "", status: "approved", agent_note: `类型: ${drama.genre || "—"}`, human_note: "", position: { x, y }, dependencies: [] });
    x += 260;
    // 剧集节点
    const episodes = drama.episodes || [];
    episodes.forEach((ep: any, i: number) => {
      const epId = `ep-${ep.id || i}`;
      imported.push({ node_id: epId, node_type: "分镜", title: ep.title || `第${i + 1}集`, content: ep.synopsis || "", status: "pending", agent_note: `第${ep.episode_number || i + 1}集`, human_note: "", position: { x, y: 80 + i * 140 }, dependencies: [`drama-${drama.id}`] });
    });
    x += 260;
    // 角色节点
    const characters = drama.characters || [];
    characters.forEach((ch: any, i: number) => {
      imported.push({ node_id: `char-${ch.id || i}`, node_type: "角色设定", title: ch.name || `角色${i + 1}`, content: ch.description || "", status: "pending", agent_note: ch.personality || "", human_note: "", position: { x, y: 80 + i * 120 }, dependencies: [`drama-${drama.id}`] });
    });
    x += 260;
    // 场景节点
    const scenes = drama.scenes || [];
    scenes.forEach((sc: any, i: number) => {
      imported.push({ node_id: `scene-${sc.id || i}`, node_type: "关键帧", title: sc.name || `场景${i + 1}`, content: sc.description || "", status: "pending", agent_note: "", human_note: "", position: { x, y: 80 + i * 120 }, dependencies: [] });
    });
    const canvasData: CanvasData = { canvas_id: `drama-import-${drama.id}`, title: drama.title, brief: drama.description || "", nodes: imported };
    setCanvas(canvasData);
    syncFlow(imported);
    setShowDramaPanel(false);
  }

  async function createCanvas() {
    if (!brief.trim()) return;
    setLoading(true);
    try {
      const token = localStorage.getItem("xagent_token");
      const resp = await fetch("/api/v1/canvas", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ brief, title: brief.slice(0, 30) }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setCanvas(data);
      syncFlow(data.nodes);
    } catch (e: any) {
      alert("创建失败: " + e.message);
    } finally { setLoading(false); }
  }

  function syncFlow(nodes: CanvasNode[]) {
    setNodes(nodes.map((n, i) => ({
      id: n.node_id,
      type: "canvasNode",
      position: n.position.x || n.position.y ? n.position : { x: 80 + i * 220, y: 150 },
      data: { node_type: n.node_type, title: n.title, status: n.status, agent_note: n.agent_note, human_note: n.human_note },
    })));
    setEdges([]);
  }

  async function handleReview(nodeId: string, status: string, humanNote: string, content?: any) {
    if (!canvas) return;
    const token = localStorage.getItem("xagent_token");
    const body: any = { status, human_note: humanNote };
    if (content !== undefined) body.content = content;
    const resp = await fetch(`/api/v1/canvas/${canvas.canvas_id}/nodes/${nodeId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    setCanvas(data);
    syncFlow(data.nodes);
    setSelectedNode(null);
  }

  async function handleGenerate(kind: "image" | "video", prompt: string) {
    if (!canvas || !selectedNode) return;
    const token = localStorage.getItem("xagent_token");
    const mode = kind === "image" ? "text_to_image" : "text_to_video";
    try {
      const resp = await fetch("/api/v1/creative-studio/media/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ kind, prompt, mode, wait: false }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = await resp.json();
      // 把生成结果写回节点 content
      const content = result.outputs?.length ? result.outputs[0] : `生成中: ${result.task_id}`;
      await handleReview(selectedNode.node_id, "modified", `已触发${kind === "image" ? "出图" : "出视频"}`, content);
    } catch (e: any) {
      alert("生成失败: " + e.message);
    }
  }

  const onNodeClick = (_: any, node: Node) => {
    if (!canvas) return;
    const found = canvas.nodes.find(n => n.node_id === node.id);
    if (found) setSelectedNode(found);
  };

  return (
    <ReactFlowProvider>
      <div className="p-6 flex flex-col h-full">
        <div className="flex items-center gap-2 mb-4">
          <h1 className="text-xl font-semibold flex-1">制作画布</h1>
          <button onClick={() => setShowDramaPanel(!showDramaPanel)}
            className="px-3 py-2 rounded text-sm border border-neutral-600 text-neutral-300 hover:border-[#d6ad62] hover:text-[#d6ad62] flex items-center gap-1 transition">
            <Clapperboard size={14} /> 短剧导入
          </button>
          <input className="flex-1 border rounded px-3 py-2 text-sm" placeholder="一句话需求，如：霸总逆袭短剧"
            value={brief} onChange={e => setBrief(e.target.value)} />
          <button onClick={createCanvas} disabled={loading || !brief.trim()}
            className="px-4 py-2 bg-brand-600 text-white rounded text-sm flex items-center gap-1 disabled:opacity-50">
            <Send size={14} /> {loading ? "生成中..." : "智能体生成"}
          </button>
        </div>

        <div className="flex-1 border rounded-md bg-white relative">
          {canvas ? (
            <ReactFlow
              nodes={nodes} edges={edges} nodeTypes={nodeTypes}
              onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
              onConnect={onConnect} onNodeClick={onNodeClick}
              fitView minZoom={0.1} maxZoom={4} panOnScroll
              defaultEdgeOptions={{ animated: true }}
            >
              <Background /> <Controls /> <MiniMap />
            </ReactFlow>
          ) : (
            <div className="h-full flex items-center justify-center text-sm text-slate-400">
              输入需求，点击"智能体生成"创建制作节点链
            </div>
          )}
        </div>

       {showDramaPanel && (
          <DramaImportPanel onImport={importDramaToCanvas} onClose={() => setShowDramaPanel(false)} />
        )}

        {selectedNode && canvas && (
          <div className="absolute right-6 top-24 z-10">
            <NodeReviewPanel
              node={selectedNode}
              onReview={(status, note, content) => handleReview(selectedNode.node_id, status, note, content)}
              onGenerate={handleGenerate}
              onClose={() => setSelectedNode(null)}
            />
          </div>
        )}
      </div>
    </ReactFlowProvider>
  );
}