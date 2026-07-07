import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Edge, Node } from "reactflow";
import {
  addClip,
  addCanvasNode,
  addTransition,
  agentClip,
  approveWorkflow,
  autoFixCanvasNode,
  batchGenerateCanvas,
  createCanvas,
  createTimeline,
  denyWorkflow,
  deleteCanvasNode,
  estimateCanvas,
  exportCanvas as exportCanvasApi,
  exportDraft,
  generateMedia,
  getMediaTask,
  importCanvas,
  parseCanvasScript,
  patchCanvasNode,
  produce,
  renderTimeline,
  requestCanvasReview,
  runCanvas,
  runCanvasStep,
  saveCanvasLayout,
  scoreCanvas,
  type EditorTimeline,
  type ProductionResult,
  type WorkflowView,
} from "../api";
import FlowCanvas from "../components/canvas/FlowCanvas";
import NodeInspector from "../components/canvas/NodeInspector";
import NodePalette from "../components/canvas/NodePalette";
import CanvasRunTimeline from "../components/canvas/CanvasRunTimeline";
import ConversationalCommand from "../components/chat/ConversationalCommand";
import { useShellActions } from "../shell/useShellStore";
import type {
  CanvasGlobalAction,
  CanvasNodeAction,
  DramaCanvasNodeData,
  DramaNodeSettings,
  DramaNodeType,
  ExecutionStatus,
} from "../components/canvas/canvasTypes";
import { createDramaNodeData } from "../components/canvas/canvasTypes";

function starterNodes(): Node<DramaCanvasNodeData>[] {
  return ["需求分析", "梗概", "角色设定", "分镜"].map((type, index) => {
    const data = createDramaNodeData(type as DramaNodeType, index + 1);
    return {
      id: data.nodeId,
      type: "dramaNode",
      position: { x: 120 + index * 300, y: 180 + (index % 2) * 140 },
      data,
    };
  });
}

function starterEdges(nodes: Node<DramaCanvasNodeData>[]): Edge[] {
  return nodes.slice(1).map((node, index) => ({
    id: `e-${nodes[index].id}-${node.id}`,
    source: nodes[index].id,
    target: node.id,
    animated: true,
  }));
}

type CreativeStudioVariant = "embedded" | "canvas";

interface CreativeStudioPageProps {
  variant?: CreativeStudioVariant;
}

export default function CreativeStudioPage({ variant = "embedded" }: CreativeStudioPageProps) {
  const isCanvasPage = variant === "canvas";
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
  const taskPolls = useRef<Map<string, number>>(new Map());
  const importFileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => () => {
    taskPolls.current.forEach((id) => window.clearInterval(id));
    taskPolls.current.clear();
  }, []);

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

  async function createCanvasFromBrief(promptOverride?: string) {
    const prompt = (promptOverride ?? brief).trim();
    if (!prompt) return;
    setBrief(prompt);
    setLoading(true);
    setError(null);
    try {
      const canvas = await createCanvas({ brief: prompt, title: prompt.slice(0, 30) || "短剧画布" });
      setCanvasId(canvas.canvas_id);
      const nextNodes = canvas.nodes.map((node, index) => {
        const data: DramaCanvasNodeData = {
          nodeId: node.node_id,
          nodeType: normalizeNodeType(node.node_type),
          title: node.title,
          content: node.content,
          dependencies: node.dependencies ?? [],
          reviewStatus: node.status === "approved" ? "approved" : node.status === "rejected" ? "rejected" : node.status === "modified" ? "modified" : node.status === "review_required" ? "review_required" : "unreviewed",
          executionStatus: "pending",
          agentNote: node.agent_note,
          humanNote: node.human_note,
          artifacts: [],
          settings: (node.settings ?? {}) as DramaCanvasNodeData["settings"],
          locked: Boolean(node.locked),
        };
        return {
          id: node.node_id,
          type: "dramaNode",
          position: node.position?.x || node.position?.y ? node.position : { x: 120 + index * 280, y: 180 },
          data,
        };
      });
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

  function updateNodeContent(nodeId: string, content: string, humanNote: string) {
    setNodes((current) => current.map((node) => node.id === nodeId
      ? { ...node, data: { ...node.data, content, humanNote, reviewStatus: "modified" } }
      : node));
    if (selectedNode?.nodeId === nodeId) {
      setSelectedNode({ ...selectedNode, content, humanNote, reviewStatus: "modified" });
    }
    if (canvasId) {
      void patchCanvasNode(canvasId, nodeId, {
        content,
        human_note: humanNote,
        status: "modified",
      }).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    }
  }

  function updateNodeSettings(nodeId: string, settings: DramaNodeSettings) {
    setNodes((current) => current.map((node) => node.id === nodeId
      ? { ...node, data: { ...node.data, settings: { ...node.data.settings, ...settings } } }
      : node));
    if (selectedNode?.nodeId === nodeId) {
      setSelectedNode({ ...selectedNode, settings: { ...selectedNode.settings, ...settings } });
    }
    if (canvasId) {
      void patchCanvasNode(canvasId, nodeId, { settings: settings as Record<string, unknown> }).catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      });
    }
  }

  function patchNodeData(nodeId: string, patch: Partial<DramaCanvasNodeData>) {
    setNodes((current) => current.map((node) => node.id === nodeId
      ? { ...node, data: { ...node.data, ...patch } }
      : node));
    if (selectedNode?.nodeId === nodeId) {
      setSelectedNode({ ...selectedNode, ...patch });
    }
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
        setError("请先在对话入口输入 brief 或剧本内容");
      return;
    }
    try {
      const result = await parseCanvasScript(canvasId, { script: brief });
      applyCanvasFromBackend({ nodes: result.canvas.nodes });
      // 把后端新建的分镜节点合并进 React 状态
      const newNodes: Node<DramaCanvasNodeData>[] = result.canvas.nodes.map((node) => {
        const existing = nodes.find((n) => n.id === node.node_id);
        if (existing) return existing;
        return {
          id: node.node_id,
          type: "dramaNode",
          position: node.position?.x || node.position?.y ? node.position : { x: 120, y: 380 },
          data: {
            nodeId: node.node_id,
            nodeType: normalizeNodeType(node.node_type),
            title: node.title,
            content: node.content,
            dependencies: node.dependencies ?? [],
            reviewStatus: "unreviewed",
            executionStatus: "pending",
            agentNote: node.agent_note,
            humanNote: node.human_note,
            artifacts: [],
          },
        };
      });
      setNodes(newNodes);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function batchGenerateMedia() {
    if (!canvasId) {
      // 退化为本地循环
      const targets = nodes.filter((node) => node.data.nodeType === "关键帧" || node.data.nodeType === "视频");
      if (!targets.length) {
        setError("画布中没有可批量生成的「关键帧」或「视频」节点");
        return;
      }
      for (const node of targets) {
        await generateForNode(node.id);
      }
      return;
    }
    try {
      const result = await batchGenerateCanvas(canvasId, ["关键帧", "视频"]);
      // 把后端返回的 task_id 映射到节点 artifacts，并启动轮询
      setNodes((current) => current.map((node) => {
        const matched = result.results.find((r) => r.node_id === node.id);
        if (!matched || matched.error || !matched.task_id) return node;
        const kind: "image" | "video" = node.data.nodeType === "视频" ? "video" : "image";
        return {
          ...node,
          data: {
            ...node.data,
            executionStatus: "running",
            artifacts: [
              ...node.data.artifacts,
              {
                id: matched.task_id,
                kind,
                title: kind === "image" ? "批量关键帧任务" : "批量视频任务",
                taskId: matched.task_id,
                status: "running",
                provider: matched.provider,
              },
            ],
          },
        };
      }));
      for (const r of result.results) {
        if (r.task_id) startTaskPolling(r.node_id, r.task_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function applyResourceEstimateAll() {
    if (!canvasId) {
      setNodes((current) => current.map((node) => {
        const estimate = estimateResourceFor(node.data);
        return { ...node, data: { ...node.data, resourceEstimate: estimate } };
      }));
      return;
    }
    try {
      const report = await estimateCanvas(canvasId);
      const byId = new Map(report.nodes.map((n) => [n.node_id, n]));
      setNodes((current) => current.map((node) => {
        const entry = byId.get(node.id);
        if (!entry) return node;
        return {
          ...node,
          data: {
            ...node.data,
            resourceEstimate: {
              vramMB: entry.vram_mb,
              timeSeconds: entry.time_seconds,
              difficulty: entry.difficulty,
            },
          },
        };
      }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function applyQualityReportAll() {
    if (!canvasId) {
      setNodes((current) => current.map((node) => {
        const report = scoreNode(node.data);
        return { ...node, data: { ...node.data, qualityReport: report } };
      }));
      return;
    }
    try {
      const report = await scoreCanvas(canvasId);
      const byId = new Map(report.nodes.map((n) => [n.node_id, n]));
      setNodes((current) => current.map((node) => {
        const entry = byId.get(node.id);
        if (!entry) return node;
        return {
          ...node,
          data: {
            ...node.data,
            qualityReport: {
              overall: entry.overall,
              connectivity: entry.connectivity,
              completeness: entry.completeness,
              parameters: entry.parameters,
              security: entry.security,
              executability: entry.executability,
              resource: entry.resource,
              issues: entry.issues,
            },
          },
        };
      }));
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
      const nextNodes: Node<DramaCanvasNodeData>[] = created.nodes.map((node, index) => ({
        id: node.node_id,
        type: "dramaNode",
        position: node.position?.x || node.position?.y ? node.position : { x: 120 + index * 280, y: 180 },
        data: {
          nodeId: node.node_id,
          nodeType: normalizeNodeType(node.node_type),
          title: node.title,
          content: node.content,
          dependencies: node.dependencies ?? [],
          reviewStatus: node.status === "approved" ? "approved" : node.status === "rejected" ? "rejected" : node.status === "modified" ? "modified" : node.status === "review_required" ? "review_required" : "unreviewed",
          executionStatus: "pending",
          agentNote: node.agent_note,
          humanNote: node.human_note,
          artifacts: [],
          settings: (node.settings ?? {}) as DramaCanvasNodeData["settings"],
          locked: Boolean(node.locked),
        },
      }));
      setNodes(nextNodes);
      // 重建 edges：根据 dependencies 生成
      const nextEdges: Edge[] = [];
      for (const node of created.nodes) {
        for (const dep of node.dependencies ?? []) {
          nextEdges.push({
            id: `e-${dep}-${node.node_id}`,
            source: dep,
            target: node.node_id,
            animated: true,
          });
        }
      }
      setEdges(nextEdges);
      setSelectedNode(null);
      setProduction(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }


  async function handleNodeAction(nodeId: string, action: CanvasNodeAction) {
    if (action === "delete") {
      setNodes((current) => current.filter((node) => node.id !== nodeId));
      setEdges((current) => current.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
      setSelectedNode(null);
      if (canvasId) {
        void deleteCanvasNode(canvasId, nodeId).catch((e: unknown) =>
          setError(e instanceof Error ? e.message : String(e)),
        );
      }
      return;
    }

    if (action === "duplicate") {
      const source = nodes.find((node) => node.id === nodeId);
      if (!source) return;
      const localId = `${source.data.nodeId}-copy-${Date.now()}`;
      const data: DramaCanvasNodeData = {
        ...source.data,
        nodeId: localId,
        title: `${source.data.title} 副本`,
        locked: false,
        executionStatus: "pending",
        reviewStatus: "unreviewed",
        artifacts: [],
      };
      setNodes((current) => [
        ...current,
        { ...source, id: localId, position: { x: source.position.x + 40, y: source.position.y + 40 }, data },
      ]);
      // 后端落地（若已有 canvasId）
      if (canvasId) {
        try {
          const updated = await addCanvasNode(canvasId, {
            node_type: source.data.nodeType,
            title: data.title,
            content: source.data.content,
            position: { x: source.position.x + 40, y: source.position.y + 40 },
          });
          const back = updated.nodes.find((n) => n.title === data.title && n.node_type === source.data.nodeType);
          if (back) {
            // 用后端真实 node_id 替换本地临时 id
            setNodes((current) => current.map((node) => node.id === localId
              ? { ...node, id: back.node_id, data: { ...node.data, nodeId: back.node_id } }
              : node));
            // 同步 settings（如果有）
            if (source.data.settings && Object.keys(source.data.settings).length) {
              void patchCanvasNode(canvasId, back.node_id, {
                settings: source.data.settings as Record<string, unknown>,
              }).catch(() => {});
            }
          }
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
      return;
    }

    if (action === "approve" || action === "reject") {
      const node = nodes.find((item) => item.id === nodeId);
      const runId = workflow?.run_id ?? node?.data.workflowRunId;
      const stepId = node?.data.workflowStepId ?? nodeId;
      if (!runId) {
        setError("请先「运行画布」生成工作流再进行审核操作");
        return;
      }
      const reviewStatus = action === "approve" ? "approved" : "rejected";
      try {
        const view = action === "approve"
          ? await approveWorkflow(runId, stepId)
          : await denyWorkflow(runId, stepId);
        applyWorkflowView(view);
        setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, reviewStatus } } : item));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
      return;
    }

    if (action === "run") {
      const node = nodes.find((item) => item.id === nodeId);
      if (node?.data.nodeType === "剪辑") {
        await runEditorForNode(nodeId);
        return;
      }
      if (node?.data.nodeType === "导出") {
        await runExportForNode(nodeId);
        return;
      }
      await runSingleStep(nodeId);
      return;
    }

    if (action === "insert-next") {
      insertNextNode(nodeId);
      return;
    }

    if (action === "rerun-downstream") {
      await rerunDownstream(nodeId);
      return;
    }

    if (action === "view-log") {
      setTimelineOpen(true);
      return;
    }

    if (action === "save-asset") {
      saveNodeArtifactsToWorkspace(nodeId);
      return;
    }

    if (action === "view-history") {
      // 简化：弹出 agentNote/humanNote 历史
      const node = nodes.find((item) => item.id === nodeId);
      if (node) setError(`生成历史：${node.data.agentNote || "暂无 agent 备注"}`);
      return;
    }

    if (action === "create-timeline" || action === "sync-upstream") {
      await runEditorForNode(nodeId);
      return;
    }

    if (action === "agent-clip") {
      await runAgentClipForNode(nodeId);
      return;
    }

    if (action === "render") {
      await runExportForNode(nodeId);
      return;
    }

    if (action === "export-draft") {
      await runExportForNode(nodeId);
      return;
    }

    if (action === "generate") {
      const node = nodes.find((item) => item.id === nodeId);
      if (node?.data.nodeType === "剪辑") {
        await runEditorForNode(nodeId);
        return;
      }
      if (node?.data.nodeType === "导出") {
        await runExportForNode(nodeId);
        return;
      }
      await generateForNode(nodeId);
      return;
    }

    // --- 新增：节点级设置 / 操作 ---
    if (action === "lock") {
      patchNodeData(nodeId, { locked: true });
      if (canvasId) {
        void patchCanvasNode(canvasId, nodeId, { locked: true }).catch((e: unknown) =>
          setError(e instanceof Error ? e.message : String(e)),
        );
      }
      return;
    }
    if (action === "unlock") {
      patchNodeData(nodeId, { locked: false });
      if (canvasId) {
        void patchCanvasNode(canvasId, nodeId, { locked: false }).catch((e: unknown) =>
          setError(e instanceof Error ? e.message : String(e)),
        );
      }
      return;
    }
    if (action === "rename") {
      const node = nodes.find((item) => item.id === nodeId);
      const next = window.prompt("重命名节点", node?.data.title ?? "");
      if (next && next.trim()) {
        patchNodeData(nodeId, { title: next.trim() });
        if (canvasId) {
          void patchCanvasNode(canvasId, nodeId, { title: next.trim() }).catch((e: unknown) =>
            setError(e instanceof Error ? e.message : String(e)),
          );
        }
      }
      return;
    }
    if (action === "stop") {
      patchNodeData(nodeId, { executionStatus: "skipped", progress: undefined });
      return;
    }
    if (action === "auto-execute") {
      const node = nodes.find((item) => item.id === nodeId);
      if (node?.data.nodeType === "剪辑") return runEditorForNode(nodeId);
      if (node?.data.nodeType === "导出") return runExportForNode(nodeId);
      return generateForNode(nodeId);
    }
    if (action === "request-review") {
      patchNodeData(nodeId, { reviewStatus: "review_required" });
      if (canvasId) {
        try {
          await requestCanvasReview(canvasId, nodeId);
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
      return;
    }
    if (action === "estimate-resource") {
      if (canvasId) {
        try {
          const report = await estimateCanvas(canvasId, [nodeId]);
          const entry = report.nodes[0];
          if (entry) {
            patchNodeData(nodeId, {
              resourceEstimate: {
                vramMB: entry.vram_mb,
                timeSeconds: entry.time_seconds,
                difficulty: entry.difficulty,
              },
            });
          }
          return;
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : String(e));
          // 回退到本地估算
        }
      }
      const node = nodes.find((item) => item.id === nodeId);
      if (node) patchNodeData(nodeId, { resourceEstimate: estimateResourceFor(node.data) });
      return;
    }
    if (action === "quality-report") {
      if (canvasId) {
        try {
          const report = await scoreCanvas(canvasId, [nodeId]);
          const entry = report.nodes[0];
          if (entry) {
            patchNodeData(nodeId, {
              qualityReport: {
                overall: entry.overall,
                connectivity: entry.connectivity,
                completeness: entry.completeness,
                parameters: entry.parameters,
                security: entry.security,
                executability: entry.executability,
                resource: entry.resource,
                issues: entry.issues,
              },
            });
          }
          return;
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
      const node = nodes.find((item) => item.id === nodeId);
      if (node) patchNodeData(nodeId, { qualityReport: scoreNode(node.data) });
      return;
    }
    if (action === "auto-fix") {
      if (canvasId) {
        try {
          const result = await autoFixCanvasNode(canvasId, nodeId);
          patchNodeData(nodeId, {
            settings: { ...(result.node.settings ?? {}) } as DramaNodeSettings,
            executionStatus: "pending",
          });
          return;
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
      const node = nodes.find((item) => item.id === nodeId);
      if (!node) return;
      const fixed = autoFixSettings(node.data);
      patchNodeData(nodeId, { settings: { ...(node.data.settings ?? {}), ...fixed }, executionStatus: "pending" });
      return;
    }
    if (action === "copy-prompt") {
      const node = nodes.find((item) => item.id === nodeId);
      const prompt = node?.data.settings?.prompt ?? String(node?.data.content ?? "");
      if (navigator.clipboard) await navigator.clipboard.writeText(prompt).catch(() => {});
      return;
    }
    if (action === "paste-prompt") {
      try {
        const text = await navigator.clipboard?.readText?.();
        if (text) updateNodeSettings(nodeId, { prompt: text });
      } catch {
        setError("无法读取剪贴板");
      }
      return;
    }
    if (
      action === "configure-prompt" ||
      action === "configure-negative" ||
      action === "configure-model" ||
      action === "configure-sampler" ||
      action === "configure-params" ||
      action === "configure-resolution" ||
      action === "configure-batch" ||
      action === "configure-strategy" ||
      action === "configure-shot" ||
      action === "configure-voice" ||
      action === "configure-bgm"
    ) {
      const node = nodes.find((item) => item.id === nodeId);
      if (node) setSelectedNode(node.data);
      return;
    }
    if (action === "preview-artifact" || action === "download-artifact") {
      const node = nodes.find((item) => item.id === nodeId);
      const artifact = node?.data.artifacts.find((art) => art.url);
      if (!artifact?.url) {
        setError("当前节点暂无可预览/下载的产物");
        return;
      }
      if (action === "preview-artifact") window.open(artifact.url, "_blank");
      else {
        const a = document.createElement("a");
        a.href = artifact.url;
        a.download = artifact.title || "artifact";
        a.click();
      }
      return;
    }
    if (action === "export-node-json") {
      const node = nodes.find((item) => item.id === nodeId);
      if (!node) return;
      const blob = new Blob([JSON.stringify(node.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${node.data.title || "node"}.json`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    if (action === "import-node-json") {
      setError("从 JSON 导入节点功能即将开放");
      return;
    }
  }

  async function generateForNode(nodeId: string) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node) return;
    if (node.data.nodeType !== "关键帧" && node.data.nodeType !== "视频") return;

    setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "running" } } : item));
    try {
      const kind = node.data.nodeType === "关键帧" ? "image" : "video";
      const mode = kind === "image" ? "text_to_image" : "text_to_video";
      const result = await generateMedia({ kind, mode, prompt: String(node.data.content || node.data.title), wait: false });
      const taskId = result.task_id || `${Date.now()}`;
      setNodes((current) => current.map((item) => item.id === nodeId ? {
        ...item,
        data: {
          ...item.data,
          executionStatus: result.status === "failed" ? "failed" : "running",
          artifacts: [
            ...item.data.artifacts,
            {
              id: taskId,
              kind,
              title: kind === "image" ? "关键帧生成任务" : "视频生成任务",
              taskId: result.task_id,
              status: result.status === "succeeded" ? "succeeded" : "running",
              url: result.outputs?.[0],
              provider: result.provider,
            },
          ],
        },
      } : item));
      if (result.task_id && result.status !== "succeeded" && result.status !== "failed") {
        startTaskPolling(nodeId, result.task_id);
      } else if (result.status === "succeeded") {
        markNodeFromTask(nodeId, taskId, result.status, result.outputs ?? []);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "failed" } } : item));
    }
  }

  function startTaskPolling(nodeId: string, taskId: string) {
    if (taskPolls.current.has(taskId)) return;
    let attempt = 0;
    const maxAttempts = 40; // ~2 分钟上限（3s * 40）
    const intervalId = window.setInterval(async () => {
      attempt += 1;
      try {
        const task = await getMediaTask(taskId);
        markNodeFromTask(nodeId, taskId, task.status, task.outputs);
        if (task.status === "succeeded" || task.status === "failed") {
          window.clearInterval(intervalId);
          taskPolls.current.delete(taskId);
          return;
        }
        if (attempt >= maxAttempts) {
          window.clearInterval(intervalId);
          taskPolls.current.delete(taskId);
          markNodeFromTask(nodeId, taskId, "failed", task.outputs);
          setError("媒体任务轮询超时，请稍后手动刷新或查看任务状态");
        }
      } catch (e: unknown) {
        window.clearInterval(intervalId);
        taskPolls.current.delete(taskId);
        setError(e instanceof Error ? e.message : String(e));
      }
    }, 3000);
    taskPolls.current.set(taskId, intervalId);
  }

  function markNodeFromTask(nodeId: string, taskId: string, status: string, outputs: string[]) {
    setNodes((current) => current.map((item) => {
      if (item.id !== nodeId) return item;
      return {
        ...item,
        data: {
          ...item.data,
          executionStatus: status === "succeeded" ? "succeeded" : status === "failed" ? "failed" : "running",
          artifacts: item.data.artifacts.map((artifact) => artifact.taskId === taskId ? {
            ...artifact,
            status: status === "succeeded" ? "succeeded" : status === "failed" ? "failed" : "running",
            url: outputs?.[0] ?? artifact.url,
          } : artifact),
        },
      };
    }));
  }

  async function runEditorForNode(nodeId: string) {
    setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "running" } } : item));
    try {
      const videoArtifacts = collectArtifacts(nodes, "video");
      const subtitleArtifacts = collectArtifacts(nodes, "subtitle");
      const audioArtifacts = collectArtifacts(nodes, "audio");

      const timeline = editorTimeline ?? await createTimeline({ name: brief.slice(0, 24) || "短剧时间线" });
      let updated: EditorTimeline = timeline;
      let cursor = 0;
      const clipIdsForTransition: string[] = [];
      for (const artifact of videoArtifacts) {
        if (!artifact.url) continue;
        const duration = Number(artifact.metadata?.duration ?? 5);
        updated = await addClip(timeline.id, {
          track_type: "video",
          source_url: artifact.url,
          timeline_start: cursor,
          timeline_end: cursor + duration,
          duration,
        });
        const last = updated.clips[updated.clips.length - 1];
        if (last) clipIdsForTransition.push(last.id);
        cursor += duration;
      }
      for (const artifact of audioArtifacts) {
        if (!artifact.url) continue;
        const duration = Number(artifact.metadata?.duration ?? Math.max(cursor, 5));
        updated = await addClip(timeline.id, {
          track_type: "audio",
          source_url: artifact.url,
          timeline_start: 0,
          timeline_end: duration,
          duration,
        });
      }
      for (const artifact of subtitleArtifacts) {
        if (!artifact.content) continue;
        const duration = Number(artifact.metadata?.duration ?? cursor);
        updated = await addClip(timeline.id, {
          track_type: "subtitle",
          source_url: "",
          timeline_start: 0,
          timeline_end: duration,
          duration,
          text: String(artifact.content),
        });
      }
      // 自动给相邻视频片段加入交叉淡入转场
      for (const clipId of clipIdsForTransition.slice(1)) {
        try {
          updated = await addTransition(timeline.id, { clip_id: clipId, type: "fade", duration: 0.5 });
        } catch {
          // 单个转场失败不影响整体
        }
      }
      setEditorTimeline(updated);
      setNodes((current) => current.map((item) => item.id === nodeId ? {
        ...item,
        data: {
          ...item.data,
          executionStatus: "succeeded",
          artifacts: replaceTimelineArtifact(item.data.artifacts, updated),
        },
      } : item));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "failed" } } : item));
    }
  }

  async function runAgentClipForNode(nodeId: string) {
    setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "running" } } : item));
    try {
      const prompt = brief.trim() || "请基于上游素材自动剪辑出 60 秒短剧";
      const result = (await agentClip({ prompt })) as { timeline_id?: string };
      setNodes((current) => current.map((item) => item.id === nodeId ? {
        ...item,
        data: {
          ...item.data,
          executionStatus: "succeeded",
          artifacts: result.timeline_id
            ? replaceTimelineArtifactById(item.data.artifacts, result.timeline_id)
            : item.data.artifacts,
        },
      } : item));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "failed" } } : item));
    }
  }

  async function runExportForNode(nodeId: string) {
    if (!editorTimeline) {
      setError("先在剪辑节点创建时间线后再导出");
      return;
    }
    setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "running" } } : item));
    try {
      const renderResult = await renderTimeline(editorTimeline.id) as { output_url?: string };
      const draftResult = await exportDraft(editorTimeline.id) as { draft_path?: string };
      setNodes((current) => current.map((item) => item.id === nodeId ? {
        ...item,
        data: {
          ...item.data,
          executionStatus: "succeeded",
          artifacts: [
            ...item.data.artifacts,
            ...(renderResult?.output_url
              ? [{ id: `${editorTimeline.id}-render`, kind: "video" as const, title: "渲染成片", url: renderResult.output_url, status: "succeeded" as const }]
              : []),
            ...(draftResult?.draft_path
              ? [{ id: `${editorTimeline.id}-draft`, kind: "draft" as const, title: "剪映草稿", url: draftResult.draft_path, status: "succeeded" as const }]
              : []),
          ],
        },
      } : item));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "failed" } } : item));
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

  async function runSingleStep(nodeId: string) {
    if (!canvasId) {
      setError("先点击「生成画布」创建画布后再运行节点");
      return;
    }
    setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "running" } } : item));
    try {
      const result = await runCanvasStep(canvasId, nodeId);
      applyWorkflowView(result.workflow);
      applyCanvasFromBackend(result.canvas);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "failed" } } : item));
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

  async function insertNextNode(sourceId: string) {
    const source = nodes.find((node) => node.id === sourceId);
    if (!source) return;
    const localId = `${Date.now()}-next`;
    const data = createDramaNodeData(source.data.nodeType, nodes.length + 1);
    data.nodeId = localId;
    const next: Node<DramaCanvasNodeData> = {
      id: localId,
      type: "dramaNode",
      position: { x: source.position.x + 280, y: source.position.y },
      data,
    };
    const edge: Edge = {
      id: `e-${sourceId}-${localId}`,
      source: sourceId,
      target: localId,
      animated: true,
    };
    setNodes((current) => [...current, next]);
    setEdges((current) => [...current, edge]);

    // 后端落地：把临时 id 替换为后端真实 node_id
    if (canvasId) {
      try {
        const updated = await addCanvasNode(canvasId, {
          node_type: source.data.nodeType,
          title: data.title,
          content: data.content,
          position: next.position,
        });
        const back = updated.nodes.find((n) => n.title === data.title);
        if (back) {
          setNodes((current) => current.map((node) => node.id === localId
            ? { ...node, id: back.node_id, data: { ...node.data, nodeId: back.node_id } }
            : node));
          // 替换 edge 的 target
          setEdges((current) => current.map((edgeItem) => edgeItem.target === localId
            ? { ...edgeItem, id: `e-${sourceId}-${back.node_id}`, target: back.node_id }
            : edgeItem));
          // 再保存一次 layout 让后端记录依赖关系
          void saveCanvasLayout(canvasId, {
            nodes: [{ node_id: back.node_id, position: next.position }],
            edges: [{ source: sourceId, target: back.node_id }],
          }).catch(() => {});
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }

  async function rerunDownstream(sourceId: string) {
    if (!canvasId) {
      setError("先生成画布后再使用「重新运行下游」");
      return;
    }
    const downstream = collectDownstream(sourceId, edges);
    for (const id of downstream) {
      await runSingleStep(id);
    }
  }

  function saveNodeArtifactsToWorkspace(nodeId: string) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node) return;
    const count = node.data.artifacts.length;
    setError(count ? `已记录 ${count} 个产物到工作区资产（占位）` : "当前节点暂无产物可保存");
  }

  if (isCanvasPage) {
    return (
      <div className="xagent-app-bg relative flex h-[100dvh] flex-col overflow-hidden text-neutral-100">
        <input
          ref={importFileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(event) => void handleImportFile(event)}
        />

        <header className="relative z-30 flex shrink-0 items-center gap-3 border-b border-white/[0.07] bg-black/72 px-4 py-3 backdrop-blur-2xl">
          <Link to="/professional?mode=workflow" className="xagent-chip shrink-0 rounded-xl px-3 py-2 text-sm">
            返回专业模式
          </Link>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-white">短剧工厂 · 无限画布</div>
            <div className="truncate text-xs text-neutral-500">独立工作台，右键画布添加节点，拖拽节点编排生成链路。</div>
          </div>
          <Link to="/editor" className="xagent-chip hidden shrink-0 rounded-xl px-3 py-2 text-sm md:inline-flex">
            高级剪辑
          </Link>
        </header>

        {error && <div className="relative z-30 border-b border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-300">{error}</div>}

        <section className="relative z-10 min-h-0 flex-1 overflow-hidden">
          <FlowCanvas
            nodes={nodes}
            edges={edges}
            onChange={handleNodesUpdate}
            onSelectNode={setSelectedNode}
            onNodeAction={handleNodeAction}
            onCanvasAction={handleCanvasAction}
          />

          <div className="absolute left-4 top-4 z-30 w-[min(36rem,calc(100%-2rem))] rounded-3xl border border-white/[0.08] bg-neutral-950/88 p-3 shadow-2xl shadow-black/45 backdrop-blur-2xl">
            <textarea
              className="field min-h-20 w-full resize-none"
              value={brief}
              onChange={(event) => setBrief(event.target.value)}
              placeholder="输入短剧 brief，例如：60 秒男频逆袭短剧，前 3 秒强钩子，结尾导出剪辑草稿..."
              aria-label="短剧 brief"
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <select className="field w-28" value={genre} onChange={(e) => setGenre(e.target.value)} aria-label="短剧类型">
                <option>逆袭</option>
                <option>霸总</option>
                <option>甜宠</option>
                <option>重生</option>
              </select>
              <select className="field w-28" value={platform} onChange={(e) => setPlatform(e.target.value)} aria-label="发布平台">
                <option>抖音</option>
                <option>快手</option>
                <option>小红书</option>
              </select>
              <button
                type="button"
                className="xagent-chip rounded-xl px-3 py-2 text-sm"
                onClick={() => setPaletteOpen((value) => !value)}
              >
                {paletteOpen ? "隐藏节点库" : "节点库"}
              </button>
              <button
                type="button"
                className="xagent-chip rounded-xl px-3 py-2 text-sm"
                onClick={runCanvasWorkflow}
                disabled={runLoading || !canvasId}
              >
                {runLoading ? "运行中" : "运行画布"}
              </button>
              <button
                type="button"
                className="xagent-chip rounded-xl px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                onClick={runProduce}
                disabled={producing || !brief.trim()}
              >
                {producing ? "产出中" : "全链路产出"}
              </button>
              <button
                type="button"
                className="gold-button rounded-xl px-4 py-2 text-sm"
                onClick={() => void createCanvasFromBrief()}
                disabled={loading || !brief.trim()}
              >
                {loading ? "生成中" : "生成画布"}
              </button>
            </div>
          </div>

          {paletteOpen && (
            <div className="xagent-scrollbar absolute bottom-4 left-4 top-72 z-20 w-[min(18rem,calc(100%-2rem))] overflow-auto rounded-3xl border border-white/[0.08] shadow-2xl shadow-black/40 backdrop-blur-2xl">
              <NodePalette onAddNode={addLocalNode} />
            </div>
          )}

          {selectedNode && (
            <div className="absolute bottom-4 right-4 top-4 z-20 hidden w-96 overflow-hidden rounded-3xl border border-white/[0.08] shadow-2xl shadow-black/50 backdrop-blur-2xl xl:block">
              <NodeInspector
                node={selectedNode}
                onClose={() => setSelectedNode(null)}
                onUpdateContent={updateNodeContent}
                onUpdateSettings={updateNodeSettings}
                onAction={handleNodeAction}
              />
            </div>
          )}

          {production?.timeline_id && (
            <a href={`/editor?timeline_id=${production.timeline_id}`} className="absolute right-4 top-4 z-30 rounded-xl border border-purple-500/30 bg-purple-500/10 px-3 py-2 text-xs text-purple-200 hover:bg-purple-500/20">
              打开高级剪辑
            </a>
          )}

          {canvasId && (
            <div className="absolute bottom-4 left-1/2 z-20 max-w-[calc(100%-2rem)] -translate-x-1/2 truncate rounded-full border border-white/[0.08] bg-neutral-950/82 px-4 py-2 font-mono text-xs text-neutral-500 shadow-2xl shadow-black/40 backdrop-blur-2xl">
              canvas {canvasId}{workflow ? ` · workflow ${workflow.run_id}` : ""}
            </div>
          )}

          {workflow && (
            <section className="absolute bottom-4 left-4 right-4 z-30 max-h-72 overflow-hidden rounded-3xl border border-white/[0.08] bg-neutral-950/90 shadow-2xl shadow-black/50 backdrop-blur-2xl lg:left-72 xl:right-[25rem]">
              <button
                type="button"
                onClick={() => setTimelineOpen((value) => !value)}
                className="flex w-full items-center justify-between px-4 py-3 text-sm text-neutral-300 hover:text-white"
              >
                <span>运行日志 · {workflow.status}</span>
                <span className="text-xs text-neutral-500">{timelineOpen ? "收起" : "展开"}</span>
              </button>
              {timelineOpen && (
                <div className="max-h-56 overflow-auto border-t border-neutral-800 p-4">
                  <CanvasRunTimeline events={workflow.timeline} />
                </div>
              )}
            </section>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-transparent text-neutral-100">
      <input
        ref={importFileRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={(event) => void handleImportFile(event)}
      />
      <header className="shrink-0 border-b border-white/[0.07] bg-black/18 px-4 py-4 backdrop-blur">
        <div className="mx-auto grid max-w-[1440px] gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <ConversationalCommand
            compact
            title="短剧导演台"
            context="输入一句话，熊宝会把目标转成画布、分镜、生成与剪辑链路"
            placeholder="例如：做一个 60 秒男频逆袭短剧，前 3 秒强钩子，最后导出剪映草稿..."
            initialAssistantMessage="把短剧目标直接告诉我，我会先沉淀为 brief，再进入画布执行。"
            suggestions={[
              "生成一个男频逆袭短剧画布",
              "拆成剧本、分镜、关键帧、视频、剪辑节点",
              "为这个短剧补质量验收节点",
            ]}
            onSubmit={(value) => {
              setBrief(value);
              return `已把「${value}」写入短剧 brief。你可以继续补充风格，也可以直接生成画布。`;
            }}
          />
          <div className="xagent-surface-subtle p-4">
            <div className="text-sm font-semibold text-white">执行参数</div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <select className="field w-full" value={genre} onChange={(e) => setGenre(e.target.value)} aria-label="短剧类型">
                <option>逆袭</option>
                <option>霸总</option>
                <option>甜宠</option>
                <option>重生</option>
              </select>
              <select className="field w-full" value={platform} onChange={(e) => setPlatform(e.target.value)} aria-label="发布平台">
                <option>抖音</option>
                <option>快手</option>
                <option>小红书</option>
              </select>
            </div>
            <div className="mt-4 grid gap-2">
              <button className="gold-button justify-center" onClick={() => void createCanvasFromBrief()} disabled={loading || !brief.trim()}>{loading ? "生成中" : "生成画布"}</button>
              <button
                className="xagent-chip justify-center"
                onClick={runCanvasWorkflow}
                disabled={runLoading || !canvasId}
              >
                {runLoading ? "运行中" : "运行画布"}
              </button>
              <button className="xagent-chip justify-center disabled:cursor-not-allowed disabled:opacity-50" onClick={runProduce} disabled={producing || !brief.trim()}>{producing ? "产出中" : "全链路产出"}</button>
            </div>
          </div>
        </div>
      </header>

      {error && <div className="border-b border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-300">{error}</div>}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {paletteOpen && <NodePalette onAddNode={addLocalNode} />}
        <div className="relative min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setPaletteOpen((value) => !value)}
            className="xagent-chip absolute left-4 top-4 z-20 rounded-xl px-3 py-2 text-xs"
          >
            {paletteOpen ? "折叠节点库" : "展开节点库"}
          </button>
          <FlowCanvas
            nodes={nodes}
            edges={edges}
            onChange={handleNodesUpdate}
            onSelectNode={setSelectedNode}
            onNodeAction={handleNodeAction}
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
          onUpdateContent={updateNodeContent}
          onUpdateSettings={updateNodeSettings}
          onAction={handleNodeAction}
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

function collectDownstream(sourceId: string, edges: Edge[]): string[] {
  const out: string[] = [];
  const visited = new Set<string>();
  const queue = [sourceId];
  while (queue.length) {
    const current = queue.shift()!;
    for (const edge of edges) {
      if (edge.source === current && !visited.has(edge.target)) {
        visited.add(edge.target);
        out.push(edge.target);
        queue.push(edge.target);
      }
    }
  }
  return out;
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

function collectArtifacts(nodes: Node<DramaCanvasNodeData>[], targetKind: string) {
  const kindMap: Record<string, DramaCanvasNodeData["nodeType"]> = {
    video: "视频",
    subtitle: "字幕",
    audio: "配音",
  };
  const nodeType = kindMap[targetKind] ?? "视频";
  const collected: DramaCanvasNodeData["artifacts"] = [];
  for (const node of nodes) {
    if (node.data.nodeType !== nodeType) continue;
    for (const artifact of node.data.artifacts) {
      if (artifact.status !== "failed") collected.push(artifact);
    }
  }
  return collected;
}

function replaceTimelineArtifact(
  artifacts: DramaCanvasNodeData["artifacts"],
  timeline: EditorTimeline,
): DramaCanvasNodeData["artifacts"] {
  const next = artifacts.filter((artifact) => artifact.kind !== "timeline");
  next.push({
    id: timeline.id,
    kind: "timeline",
    title: timeline.name || "短剧时间线",
    status: "succeeded",
    metadata: { duration: timeline.total_duration, clips: timeline.clips.length },
  });
  return next;
}

function replaceTimelineArtifactById(
  artifacts: DramaCanvasNodeData["artifacts"],
  timelineId: string,
): DramaCanvasNodeData["artifacts"] {
  const next = artifacts.filter((artifact) => artifact.kind !== "timeline");
  next.push({
    id: timelineId,
    kind: "timeline",
    title: "智能体生成时间线",
    status: "succeeded",
  });
  return next;
}

function normalizeNodeType(value: string): DramaNodeType {
  const allowed: DramaNodeType[] = ["需求分析", "梗概", "角色设定", "分镜", "关键帧", "视频", "配音", "字幕", "配乐", "剪辑", "导出"];
  return allowed.includes(value as DramaNodeType) ? value as DramaNodeType : "需求分析";
}

/**
 * 节点资源估算 —— 参考 X-Agent 视觉工作流的简化模型：
 * 关键帧/视频按分辨率 × 步数 × 批量估显存与耗时；其它节点按经验值。
 */
function estimateResourceFor(data: DramaCanvasNodeData) {
  const settings = data.settings ?? {};
  switch (data.nodeType) {
    case "关键帧": {
      const [w, h] = parseResolution(settings.resolution, [1024, 1024]);
      const pixels = (w * h) / (1024 * 1024);
      const steps = settings.steps ?? 28;
      const batch = settings.batch ?? 1;
      const vramMB = Math.round(2200 + pixels * 1800 * batch);
      const timeSeconds = Math.round((pixels * steps * batch) * 0.35);
      return { vramMB, timeSeconds, difficulty: pickDifficulty(vramMB) };
    }
    case "视频": {
      const [w, h] = parseResolution(settings.resolution, [1280, 720]);
      const pixels = (w * h) / (1024 * 1024);
      const duration = settings.duration ?? 5;
      const steps = settings.steps ?? 24;
      const batch = settings.batch ?? 1;
      const vramMB = Math.round(8000 + pixels * 3200 * batch);
      const timeSeconds = Math.round(pixels * duration * steps * batch * 1.2);
      return { vramMB, timeSeconds, difficulty: pickDifficulty(vramMB) };
    }
    case "配音":
      return { vramMB: 800, timeSeconds: Math.round((settings.duration ?? 6) * 1.2), difficulty: "low" as const };
    case "配乐":
      return { vramMB: 1500, timeSeconds: Math.round((settings.duration ?? 30) * 0.8), difficulty: "low" as const };
    case "字幕":
      return { vramMB: 200, timeSeconds: 5, difficulty: "low" as const };
    case "分镜":
      return { vramMB: 200, timeSeconds: 8, difficulty: "low" as const };
    case "剪辑":
    case "导出":
      return { vramMB: 600, timeSeconds: 30, difficulty: "medium" as const };
    default:
      return { vramMB: 100, timeSeconds: 6, difficulty: "low" as const };
  }
}

function parseResolution(value: string | undefined, fallback: [number, number]): [number, number] {
  if (!value) return fallback;
  const match = value.match(/(\d+)\s*[x×*]\s*(\d+)/i);
  if (!match) return fallback;
  return [Number(match[1]), Number(match[2])];
}

function pickDifficulty(vramMB: number): "low" | "medium" | "high" {
  if (vramMB >= 14000) return "high";
  if (vramMB >= 6000) return "medium";
  return "low";
}

/** 节点质量评分 —— 简化的连通性/完整性/参数维度评估 */
function scoreNode(data: DramaCanvasNodeData) {
  const settings = data.settings ?? {};
  const hasPrompt = Boolean((settings.prompt ?? "").trim()) || Boolean(String(data.content ?? "").trim());
  const hasDeps = data.dependencies.length > 0 || ["需求分析", "梗概"].includes(data.nodeType);
  const paramComplete = data.nodeType === "关键帧" || data.nodeType === "视频"
    ? Boolean(settings.sampler && settings.steps && settings.cfg)
    : true;
  const connectivity = hasDeps ? 95 : 65;
  const completeness = hasPrompt ? 92 : 50;
  const parameters = paramComplete ? 90 : 60;
  const security = 95;
  const executability = data.executionStatus === "failed" ? 40 : 88;
  const resource = data.resourceEstimate?.difficulty === "high" ? 70 : 90;
  const overall = Math.round((connectivity + completeness + parameters + security + executability + resource) / 6);
  const issues: string[] = [];
  if (!hasPrompt) issues.push("提示词为空");
  if (!paramComplete) issues.push("采样参数不完整");
  if (data.executionStatus === "failed") issues.push("最近一次执行失败");
  return { overall, connectivity, completeness, parameters, security, executability, resource, issues };
}

/** 简化的自动修复：补齐缺失的关键参数 */
function autoFixSettings(data: DramaCanvasNodeData): DramaNodeSettings {
  const settings = data.settings ?? {};
  const fix: DramaNodeSettings = {};
  if (data.nodeType === "关键帧") {
    if (!settings.sampler) fix.sampler = "euler_a";
    if (!settings.scheduler) fix.scheduler = "karras";
    if (!settings.steps) fix.steps = 28;
    if (!settings.cfg) fix.cfg = 6.5;
    if (!settings.resolution) fix.resolution = "1024x1024";
    if (!settings.batch) fix.batch = 1;
  } else if (data.nodeType === "视频") {
    if (!settings.sampler) fix.sampler = "dpmpp_2m";
    if (!settings.scheduler) fix.scheduler = "sgm_uniform";
    if (!settings.steps) fix.steps = 24;
    if (!settings.cfg) fix.cfg = 6.0;
    if (!settings.resolution) fix.resolution = "1280x720";
    if (!settings.duration) fix.duration = 5;
  }
  if (!settings.strategy) fix.strategy = "balanced";
  if (!settings.prompt) fix.prompt = String(data.content ?? "") || data.title;
  return fix;
}
