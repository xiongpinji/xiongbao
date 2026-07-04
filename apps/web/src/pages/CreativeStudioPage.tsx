import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Edge, Node } from "reactflow";
import {
  createCanvas,
  exportCanvas as exportCanvasApi,
  importCanvas,
  parseCanvasScript,
  produce,
  runCanvas,
  saveCanvasLayout,
  type CanvasNodeDTO,
  type EditorTimeline,
  type ProductionResult,
  type WorkflowView,
} from "../api";
import FlowCanvas from "../components/canvas/FlowCanvas";
import NodeInspector from "../components/canvas/NodeInspector";
import NodePalette from "../components/canvas/NodePalette";
import CanvasRunTimeline from "../components/canvas/CanvasRunTimeline";
import { useShellActions } from "../shell/useShellStore";
import type {
  CanvasGlobalAction,
  DramaCanvasNodeData,
  DramaNodeType,
  ExecutionStatus,
} from "../components/canvas/canvasTypes";
import { createDramaNodeData } from "../components/canvas/canvasTypes";
import { mapCanvasNodeToFlowNode, mapDependenciesToEdges } from "./creativeStudio/creativeCanvasMappers";
import { useCreativeMediaTasks } from "./creativeStudio/useCreativeMediaTasks";
import { useCreativeNodeActions } from "./creativeStudio/useCreativeNodeActions";
import { useCreativeEditorBridge } from "./creativeStudio/useCreativeEditorBridge";
import { starterEdges, starterNodes } from "./creativeStudio/creativeCanvasStarters";

const previewMessage = "当前输入会优先生成创作草案与页面节点意图；正式生产链路仍以明确的执行按钮和后端返回结果为准。";
const executionBoundaryMessage = "“创建画布”用于生成草案；“执行 / 生产”才会进入真实后端链路。";

function mapBackendNodesByExistingFlow(
  backendNodes: CanvasNodeDTO[],
  existingNodes: Node<DramaCanvasNodeData>[],
  fallbackPosition: { x: number; y: number },
  reviewStatus: DramaCanvasNodeData["reviewStatus"],
): Node<DramaCanvasNodeData>[] {
  return backendNodes.map((node, index) => {
    const existing = existingNodes.find((item) => item.id === node.node_id);
    return existing ?? mapCanvasNodeToFlowNode(node, index, { fallbackPosition, reviewStatus });
  });
}

export default function CreativeStudioPage() {
  const navigate = useNavigate();
  const { syncRunTask } = useShellActions();
  const initial = useMemo(() => starterNodes(), []);
  const [brief, setBrief] = useState("");
  const [genre, setGenre] = useState("逆袭");
  const [platform, setPlatform] = useState("抖音");
  const [canvasId, setCanvasId] = useState<string | null>(null);
  const [nodes, setNodes] = useState<Node<DramaCanvasNodeData>[]>(initial);
  const [edges, setEdges] = useState<Edge[]>(starterEdges(initial));
  const [selectedNode, setSelectedNode] = useState<DramaCanvasNodeData | null>(null);
  const [production, setProduction] = useState<ProductionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [producing, setProducing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(true);
  const [workflow, setWorkflow] = useState<WorkflowView | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [editorTimeline, setEditorTimeline] = useState<EditorTimeline | null>(null);
  const layoutDebounce = useRef<number | null>(null);
  const importFileRef = useRef<HTMLInputElement | null>(null);

  const {
    batchGenerateMedia,
    applyResourceEstimateAll,
    applyQualityReportAll,
    generateForNode,
    estimateResourceFor,
    scoreNode,
    startTaskPolling,
  } = useCreativeMediaTasks({
    canvasId,
    nodes,
    setNodes,
    setError,
  });
  void startTaskPolling;

  const { runEditorForNode, runExportForNode, runAgentClipForNode } = useCreativeEditorBridge({
    brief,
    nodes,
    editorTimeline,
    setEditorTimeline,
    setNodes,
    setError,
  });

  useEffect(() => {
    if (!canvasId) return;
    if (layoutDebounce.current) window.clearTimeout(layoutDebounce.current);
    layoutDebounce.current = window.setTimeout(() => {
      void saveCanvasLayout(canvasId, {
        nodes: nodes.map((node) => ({ node_id: node.id, position: { x: node.position.x, y: node.position.y } })),
        edges: edges.map((edge) => ({ source: edge.source, target: edge.target })),
      }).catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      });
    }, 600);
    return () => {
      if (layoutDebounce.current) window.clearTimeout(layoutDebounce.current);
    };
  }, [canvasId, nodes, edges]);

  async function createCanvasFromBrief() {
    if (!brief.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const canvas = await createCanvas({ brief, title: brief.slice(0, 30) || "短剧画布" });
      setCanvasId(canvas.canvas_id);
      const nextNodes = canvas.nodes.map((node, index) => mapCanvasNodeToFlowNode(node, index));
      setNodes(nextNodes);
      setEdges([]);
      setSelectedNode(null);
      setProduction(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function runProduce() {
    if (!brief.trim()) return;
    setProducing(true);
    setError(null);
    try {
      const result = await produce({ brief, genre, platform, with_video: true });
      setProduction(result);
      appendProductionArtifacts(result);
      const runId = result.run_id ?? result.task_id ?? result.storyboard_id;
      syncRunTask(runId, { source: "creative" });
      navigate(`/runs/${encodeURIComponent(runId)}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setProducing(false);
    }
  }

  function appendProductionArtifacts(result: ProductionResult) {
    const timelineId = result.timeline_id;
    if (!timelineId) return;
    setNodes((current) => current.map((node) => {
      if (node.data.nodeType !== "剪辑") return node;
      const hasTimeline = node.data.artifacts.some((artifact) => artifact.id === timelineId);
      if (hasTimeline) return node;
      return {
        ...node,
        data: {
          ...node.data,
          artifacts: [
            ...node.data.artifacts,
            { id: timelineId, kind: "timeline" as const, title: "全链路产出时间线", status: "succeeded" as const },
          ],
        },
      };
    }));
  }

  function addLocalNode(type: DramaNodeType) {
    const data = createDramaNodeData(type, nodes.length + 1);
    setNodes((current) => [
      ...current,
      {
        id: data.nodeId,
        type: "dramaNode",
        position: { x: 160 + current.length * 40, y: 220 + current.length * 30 },
        data,
      },
    ]);
    setSelectedNode(data);
  }

  function handleNodesUpdate(nextNodes: Node<DramaCanvasNodeData>[], nextEdges: Edge[]) {
    setNodes(nextNodes);
    setEdges(nextEdges);
  }

  function handleCanvasAction(action: CanvasGlobalAction) {
    switch (action) {
      case "auto-layout":
        autoLayoutNodes();
        return;
      case "toggle-palette":
        setPaletteOpen((value) => !value);
        return;
      case "run-all":
      case "auto-execute-all":
        void runCanvasWorkflow();
        return;
      case "parse-script": {
        void parseScriptFromBrief();
        return;
      }
      case "batch-generate":
        void batchGenerateMedia();
        return;
      case "resource-estimate-all":
        void applyResourceEstimateAll();
        return;
      case "quality-report-all":
        void applyQualityReportAll();
        return;
      case "global-settings":
        setError("全局参数面板将在后续版本中开放，可在节点 Inspector 中按节点调整");
        return;
      case "export-canvas":
        void exportCanvasJson();
        return;
      case "import-canvas":
        triggerImportFilePicker();
        return;
      case "clear-canvas":
        setNodes([]);
        setEdges([]);
        setSelectedNode(null);
        return;
      default:
        return;
    }
  }

  function autoLayoutNodes() {
    const order: DramaNodeType[] = ["需求分析", "梗概", "角色设定", "分镜", "关键帧", "视频", "配音", "字幕", "配乐", "剪辑", "导出"];
    const buckets = new Map<DramaNodeType, Node<DramaCanvasNodeData>[]>();
    for (const node of nodes) {
      const list = buckets.get(node.data.nodeType) ?? [];
      list.push(node);
      buckets.set(node.data.nodeType, list);
    }
    let col = 0;
    const next: Node<DramaCanvasNodeData>[] = [];
    for (const type of order) {
      const list = buckets.get(type);
      if (!list?.length) continue;
      list.forEach((node, row) => {
        next.push({ ...node, position: { x: 120 + col * 280, y: 120 + row * 200 } });
      });
      col += 1;
    }
    // 把未在 order 中的节点附在末列
    for (const node of nodes) {
      if (!next.find((item) => item.id === node.id)) next.push(node);
    }
    setNodes(next);
  }

  async function parseScriptFromBrief() {
    if (!canvasId) {
      setError("请先生成画布后再使用「剧本解析」");
      return;
    }
    if (!brief.trim()) {
      setError("请先在顶部输入 brief 或剧本内容");
      return;
    }
    try {
      const result = await parseCanvasScript(canvasId, { script: brief });
      applyCanvasFromBackend({ nodes: result.canvas.nodes });
      // 把后端新建的分镜节点合并进 React 状态
      const newNodes = mapBackendNodesByExistingFlow(result.canvas.nodes, nodes, { x: 120, y: 380 }, "unreviewed");
      setNodes(newNodes);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function exportCanvasJson() {
    try {
      const payload = canvasId
        ? await exportCanvasApi(canvasId)
        : {
          canvasId,
          brief,
          nodes: nodes.map((node) => ({ id: node.id, position: node.position, data: node.data })),
          edges,
        };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `canvas-${canvasId ?? "draft"}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function triggerImportFilePicker() {
    importFileRef.current?.click();
  }

  async function handleImportFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    event.target.value = ""; // 允许下次重新选同一文件
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as {
        title?: string;
        brief?: string;
        nodes?: Record<string, unknown>[];
        edges?: { source: string; target: string }[];
      };
      if (!Array.isArray(parsed.nodes) || !parsed.nodes.length) {
        setError("导入失败：JSON 中未找到 nodes 数组");
        return;
      }
      const created = await importCanvas({
        title: parsed.title ?? "导入画布",
        brief: parsed.brief ?? "",
        nodes: parsed.nodes,
        edges: parsed.edges ?? [],
      });
      // 用后端返回的画布替换当前视图
      setCanvasId(created.canvas_id);
      const nextNodes: Node<DramaCanvasNodeData>[] = created.nodes.map((node, index) => mapCanvasNodeToFlowNode(node, index));
      setNodes(nextNodes);
      setEdges(mapDependenciesToEdges(created.nodes));
      setSelectedNode(null);
      setProduction(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function applyWorkflowView(view: WorkflowView) {
    setWorkflow(view);
    const statusMap = new Map(view.steps.map((step) => [step.id, step.status]));
    setNodes((current) => current.map((node) => {
      const status = statusMap.get(node.id);
      if (!status) return node;
      const executionStatus = mapWorkflowStatus(status);
      const reviewStatus = status === "awaiting_approval" && node.data.reviewStatus === "unreviewed"
        ? "review_required"
        : node.data.reviewStatus;
      return {
        ...node,
        data: {
          ...node.data,
          executionStatus,
          reviewStatus,
          workflowRunId: view.run_id,
          workflowStepId: node.id,
        },
      };
    }));
  }

  async function runCanvasWorkflow() {
    if (!canvasId) {
      setError("请先生成画布或在画布上创建节点后再运行");
      return;
    }
    setRunLoading(true);
    setError(null);
    try {
      const result = await runCanvas(canvasId);
      applyWorkflowView(result.workflow);
      applyCanvasFromBackend(result.canvas);
      setTimelineOpen(true);
      syncRunTask(result.workflow.run_id, { source: "creative" });
      navigate(`/runs/${encodeURIComponent(result.workflow.run_id)}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunLoading(false);
    }
  }

  function applyCanvasFromBackend(payload: { nodes: { node_id: string; agent_note?: string; human_note?: string; content?: unknown }[] }) {
    setNodes((current) => current.map((item) => {
      const back = payload.nodes.find((n) => n.node_id === item.id);
      if (!back) return item;
      return {
        ...item,
        data: {
          ...item.data,
          agentNote: back.agent_note ?? item.data.agentNote,
          humanNote: back.human_note ?? item.data.humanNote,
          content: back.content !== undefined ? back.content : item.data.content,
        },
      };
    }));
  }

  const { updateNodeContent, updateNodeSettings, patchNodeData, handleNodeAction } = useCreativeNodeActions({
    canvasId,
    nodes,
    edges,
    workflow,
    selectedNode,
    setNodes,
    setEdges,
    setSelectedNode,
    setError,
    setTimelineOpen,
    applyWorkflowView,
    applyCanvasFromBackend,
    generateForNode,
    estimateResourceFor,
    scoreNode,
    runEditorForNode,
    runAgentClipForNode,
    runExportForNode,
  });
  const nodeActionBindings = {
    updateNodeContent,
    updateNodeSettings,
    patchNodeData,
    handleNodeAction,
  };

  return (
    <div className="flex h-full flex-col bg-neutral-950 text-neutral-100">
      <input
        ref={importFileRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={(event) => void handleImportFile(event)}
      />
      <header className="grid shrink-0 gap-3 border-b border-neutral-800 bg-neutral-950 px-4 py-3 lg:grid-cols-[minmax(220px,1fr)_minmax(320px,640px)_112px_112px_auto_auto_auto] lg:items-center">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-white">短剧工厂自由画布</div>
          <div className="text-xs text-neutral-500">节点、连线、审核、媒体生成、剪辑与导出都在画布中完成</div>
        </div>
        <input className="field w-full" value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="一句话 brief，例如：霸总逆袭短剧" />
        <select className="field w-full" value={genre} onChange={(e) => setGenre(e.target.value)}>
          <option>逆袭</option>
          <option>霸总</option>
          <option>甜宠</option>
          <option>重生</option>
        </select>
        <select className="field w-full" value={platform} onChange={(e) => setPlatform(e.target.value)}>
          <option>抖音</option>
          <option>快手</option>
          <option>小红书</option>
        </select>
        <button className="primary-button whitespace-nowrap" onClick={createCanvasFromBrief} disabled={loading || !brief.trim()}>{loading ? "生成中" : "创建画布"}</button>
        <button
          className="rounded-xl border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-sm text-blue-200 transition hover:bg-blue-500/20 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
          onClick={runCanvasWorkflow}
          disabled={runLoading || !canvasId}
        >
          {runLoading ? "执行中" : "执行画布"}
        </button>
        <button className="whitespace-nowrap rounded-xl border border-neutral-700 px-3 py-2 text-sm text-neutral-200 transition hover:bg-neutral-800 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50" onClick={runProduce} disabled={producing || !brief.trim()}>{producing ? "生产中" : "生产内容"}</button>
      </header>

      <div className="border-b border-neutral-800 bg-neutral-950/80 px-4 py-3">
        <div className="rounded-2xl border border-fuchsia-500/20 bg-fuchsia-500/10 px-4 py-3 text-sm leading-6 text-fuchsia-100">
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-fuchsia-200/80">创作草案 / 生产执行边界</div>
          <p className="mt-3">{previewMessage}</p>
          <p className="mt-2 text-fuchsia-50/90">{executionBoundaryMessage}</p>
        </div>
      </div>

      {error && <div className="border-b border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-300">{error}</div>}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {paletteOpen && <NodePalette onAddNode={addLocalNode} />}
        <div className="relative min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setPaletteOpen((value) => !value)}
            className="absolute left-4 top-4 z-20 rounded-xl border border-neutral-700 bg-neutral-900 px-3 py-2 text-xs text-neutral-300 hover:bg-neutral-800"
          >
            {paletteOpen ? "折叠节点库" : "展开节点库"}
          </button>
          <FlowCanvas
            nodes={nodes}
            edges={edges}
            onChange={handleNodesUpdate}
            onSelectNode={setSelectedNode}
            onNodeAction={nodeActionBindings.handleNodeAction}
            onCanvasAction={handleCanvasAction}
          />
          {production?.timeline_id && (
            <a href={`/editor?timeline_id=${production.timeline_id}`} className="absolute right-4 top-4 z-20 rounded-xl border border-purple-500/30 bg-purple-500/10 px-3 py-2 text-xs text-purple-200 hover:bg-purple-500/20">
              打开高级剪辑
            </a>
          )}
        </div>
        <NodeInspector
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          onUpdateContent={nodeActionBindings.updateNodeContent}
          onUpdateSettings={nodeActionBindings.updateNodeSettings}
          onAction={nodeActionBindings.handleNodeAction}
        />
      </div>

      {canvasId && <div className="border-t border-neutral-800 bg-neutral-950 px-4 py-2 font-mono text-xs text-neutral-600">canvas {canvasId}{workflow ? `  ·  workflow ${workflow.run_id}` : ""}</div>}

      {workflow && (
        <section className="border-t border-neutral-800 bg-neutral-950">
          <button
            type="button"
            onClick={() => setTimelineOpen((value) => !value)}
            className="flex w-full items-center justify-between px-4 py-2 text-sm text-neutral-300 hover:text-white"
          >
            <span>运行日志 · {workflow.status}</span>
            <span className="text-xs text-neutral-500">{timelineOpen ? "收起" : "展开"}</span>
          </button>
          {timelineOpen && (
            <div className="border-t border-neutral-800 p-4">
              <CanvasRunTimeline events={workflow.timeline} />
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function mapWorkflowStatus(status: string): ExecutionStatus {
  switch (status) {
    case "pending":
    case "running":
    case "awaiting_approval":
    case "succeeded":
    case "failed":
    case "skipped":
    case "compensated":
      return status;
    default:
      return "pending";
  }
}
