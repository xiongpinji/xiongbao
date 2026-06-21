import { useState } from "react";
import ReactFlow, { Background, Controls, type Node, type Edge } from "reactflow";
import "reactflow/dist/style.css";
import {
  createDraft,
  produce,
  reviewDraft,
  type ProductionResult,
  type WorkflowDraft,
} from "../api";

const RISK_COLOR: Record<string, string> = {
  low: "#10b981",
  medium: "#f59e0b",
  high: "#ef4444",
};

function toFlow(draft: WorkflowDraft): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = draft.nodes.map((n, i) => ({
    id: n.node_id,
    position: { x: 80, y: 60 + i * 110 },
    data: {
      label: (
        <div className="text-xs">
          <div className="font-medium">{n.node_type}</div>
          <div className="text-slate-500">{n.agent_role} · {n.provider_kind}</div>
          {n.needs_review && <div className="text-amber-600 mt-1">需审核</div>}
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
  const [production, setProduction] = useState<ProductionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [producing, setProducing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    if (!brief.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setDraft(await createDraft({ brief, genre, platform }));
      setProduction(null);
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

  async function runProduce() {
    if (!brief.trim()) return;
    setProducing(true);
    setError(null);
    try {
      setProduction(await produce({ brief, genre, platform, with_video: true }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setProducing(false);
    }
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
        <select className="border rounded px-2 text-sm" value={genre} onChange={(e) => setGenre(e.target.value)}>
          <option>逆袭</option>
          <option>霸总</option>
          <option>甜宠</option>
          <option>重生</option>
        </select>
        <select className="border rounded px-2 text-sm" value={platform} onChange={(e) => setPlatform(e.target.value)}>
          <option>抖音</option>
          <option>快手</option>
          <option>小红书</option>
        </select>
        <button className="px-4 py-2 bg-brand-600 text-white rounded text-sm disabled:opacity-50" onClick={generate} disabled={loading || !brief.trim()}>
          {loading ? "生成中..." : "生成草稿"}
        </button>
        <button className="px-4 py-2 bg-purple-600 text-white rounded text-sm disabled:opacity-50" onClick={runProduce} disabled={producing || !brief.trim()}>
          {producing ? "产出中..." : "全链路产出"}
        </button>
      </div>

      {error && <div className="text-sm text-red-600 mb-3">{error}</div>}

      {/* 全链路产出结果 */}
      {production && (
        <div className="mb-4 bg-white border rounded-md p-4">
          <div className="flex items-center gap-3 mb-3">
            <span className="font-medium text-sm">{production.title}</span>
            <span className={`text-xs px-2 py-0.5 rounded ${production.status === "produced" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
              {production.status === "produced" ? "完成" : "部分完成"}
            </span>
            <span className="text-xs text-slate-500">{production.shots.length} 镜头</span>
            {production.quality_passed && <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">质量门通过</span>}
            {production.timeline_id && (
              <a href="/editor" className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded hover:bg-purple-200">
                → 打开剪辑工作台
              </a>
            )}
          </div>
          <div className="space-y-3">
            {production.shots.map((shot, i) => (
              <div key={shot.shot_id} className="flex gap-3 border-t pt-3">
                <div className="text-xs text-slate-400 w-6">#{i + 1}</div>
                <div className="flex-1">
                  <div className="text-xs text-slate-600">{shot.scene}</div>
                  <div className="text-xs text-slate-400 mt-0.5">图：{shot.image_prompt}</div>
                  {/* 关键帧 */}
                  {shot.image_outputs.length > 0 && (
                    <div className="flex gap-1 mt-1">
                      {shot.image_outputs.map((url, j) => (
                        <div key={j} className="text-xs bg-slate-100 px-2 py-1 rounded text-slate-500">
                          🖼 {url.startsWith("placeholder") ? "占位图" : "图"}
                        </div>
                      ))}
                    </div>
                  )}
                  {shot.image_error && <div className="text-xs text-red-500 mt-1">图错误：{shot.image_error}</div>}
                  {/* 视频 */}
                  {shot.video_outputs.length > 0 && (
                    <div className="flex gap-1 mt-1">
                      {shot.video_outputs.map((url, j) => (
                        <div key={j} className="text-xs bg-purple-50 px-2 py-1 rounded text-purple-600">
                          🎬 {url.startsWith("placeholder") ? "占位视频" : "视频"}
                        </div>
                      ))}
                    </div>
                  )}
                  {shot.video_error && <div className="text-xs text-red-500 mt-1">视频错误：{shot.video_error}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 草稿审阅 */}
      {draft && (
        <div className="flex items-center gap-2 mb-3 text-sm">
          状态：<span className="font-medium">{draft.status}</span>
          {draft.status === "pending_review" && (
            <>
              <button className="px-3 py-1 bg-green-600 text-white rounded text-xs" onClick={() => review(true)}>审核通过</button>
              <button className="px-3 py-1 bg-red-600 text-white rounded text-xs" onClick={() => review(false)}>驳回</button>
            </>
          )}
        </div>
      )}

      {/* 节点画布 */}
      <div className="flex-1 border rounded-md bg-white">
        {flow ? (
          <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView>
            <Background />
            <Controls />
          </ReactFlow>
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-slate-400">
            生成草稿或全链路产出后在此显示节点画布
          </div>
        )}
      </div>
    </div>
  );
}
