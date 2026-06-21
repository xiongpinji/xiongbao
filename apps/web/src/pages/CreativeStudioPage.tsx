import { useState } from "react";
import ReactFlow, { Background, Controls, type Node, type Edge } from "reactflow";
import "reactflow/dist/style.css";
import { createDraft, reviewDraft, type WorkflowDraft } from "../api";

const RISK_COLOR: Record<string, string> = {
  low: "#10b981",
  medium: "#f59e0b",
  high: "#ef4444",
};

// 把草稿节点链布局成 React Flow 节点/边
function toFlow(draft: WorkflowDraft): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = draft.nodes.map((n, i) => ({
    id: n.node_id,
    position: { x: 80, y: 60 + i * 110 },
    data: {
      label: (
        <div className="text-xs">
          <div className="font-medium">{n.node_type}</div>
          <div className="text-slate-500">{n.agent_role} · {n.provider_kind}</div>
          {n.needs_review && (
            <div className="text-amber-600 mt-1">需审核</div>
          )}
        </div>
      ),
    },
    style: {
      borderLeft: `4px solid ${RISK_COLOR[n.risk_level] ?? "#94a3b8"}`,
      width: 200,
    },
  }));
  const edges: Edge[] = draft.nodes.slice(1).map((n) => ({
    id: `e-${n.node_id}`,
    source: draft.nodes[draft.nodes.indexOf(n) - 1].node_id,
    target: n.node_id,
    animated: true,
  }));
  return { nodes, edges };
}

export default function CreativeStudioPage() {
  const [brief, setBrief] = useState("");
  const [genre, setGenre] = useState("逆袭");
  const [platform, setPlatform] = useState("抖音");
  const [draft, setDraft] = useState<WorkflowDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    if (!brief.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setDraft(await createDraft({ brief, genre, platform }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function review(approved: boolean) {
    if (!draft) return;
    setDraft(await reviewDraft(draft.draft_id, approved));
  }

  const flow = draft ? toFlow(draft) : null;

  return (
    <div className="p-6 flex flex-col h-full">
      <h1 className="text-xl font-semibold mb-4">短剧工厂</h1>
      <div className="flex gap-2 mb-4">
        <input
          className="flex-1 border rounded px-3 py-2 text-sm"
          placeholder="一句话 brief，例如：霸总逆袭短剧"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
        />
        <select
          className="border rounded px-2 text-sm"
          value={genre}
          onChange={(e) => setGenre(e.target.value)}
        >
          <option>逆袭</option>
          <option>霸总</option>
          <option>甜宠</option>
          <option>重生</option>
        </select>
        <select
          className="border rounded px-2 text-sm"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
        >
          <option>抖音</option>
          <option>快手</option>
          <option>小红书</option>
        </select>
        <button
          className="px-4 py-2 bg-brand-600 text-white rounded text-sm disabled:opacity-50"
          onClick={generate}
          disabled={loading || !brief.trim()}
        >
          {loading ? "生成中..." : "生成草稿"}
        </button>
      </div>

      {error && <div className="text-sm text-red-600 mb-3">{error}</div>}

      {draft && (
        <div className="flex items-center gap-2 mb-3 text-sm">
          状态：<span className="font-medium">{draft.status}</span>
          {draft.status === "pending_review" && (
            <>
              <button
                className="px-3 py-1 bg-green-600 text-white rounded text-xs"
                onClick={() => review(true)}
              >
                审核通过
              </button>
              <button
                className="px-3 py-1 bg-red-600 text-white rounded text-xs"
                onClick={() => review(false)}
              >
                驳回
              </button>
            </>
          )}
        </div>
      )}

      <div className="flex-1 border rounded-md bg-white">
        {flow ? (
          <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView>
            <Background />
            <Controls />
          </ReactFlow>
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-slate-400">
            生成草稿后在此显示节点画布
          </div>
        )}
      </div>
    </div>
  );
}
