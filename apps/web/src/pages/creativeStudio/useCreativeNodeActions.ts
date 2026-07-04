import { useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Edge, Node } from "reactflow";
import {
  addCanvasNode,
  approveWorkflow,
  autoFixCanvasNode,
  deleteCanvasNode,
  denyWorkflow,
  estimateCanvas,
  patchCanvasNode,
  requestCanvasReview,
  runCanvasStep,
  saveCanvasLayout,
  scoreCanvas,
  type WorkflowView,
} from "../../api";
import {
  createDramaNodeData,
  type CanvasNodeAction,
  type DramaCanvasNodeData,
  type DramaNodeSettings,
  type QualityReport,
  type ResourceEstimate,
} from "../../components/canvas/canvasTypes";

interface BackendNodeUpdate {
  node_id: string;
  agent_note?: string;
  human_note?: string;
  content?: unknown;
}

interface UseCreativeNodeActionsParams {
  canvasId: string | null;
  nodes: Node<DramaCanvasNodeData>[];
  edges: Edge[];
  workflow: WorkflowView | null;
  selectedNode: DramaCanvasNodeData | null;
  setNodes: Dispatch<SetStateAction<Node<DramaCanvasNodeData>[]>>;
  setEdges: Dispatch<SetStateAction<Edge[]>>;
  setSelectedNode: Dispatch<SetStateAction<DramaCanvasNodeData | null>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setTimelineOpen: Dispatch<SetStateAction<boolean>>;
  applyWorkflowView: (view: WorkflowView) => void;
  applyCanvasFromBackend: (payload: { nodes: BackendNodeUpdate[] }) => void;
  generateForNode: (nodeId: string) => Promise<void>;
  estimateResourceFor: (data: DramaCanvasNodeData) => ResourceEstimate;
  scoreNode: (data: DramaCanvasNodeData) => QualityReport;
  runEditorForNode: (nodeId: string) => Promise<void>;
  runAgentClipForNode: (nodeId: string) => Promise<void>;
  runExportForNode: (nodeId: string) => Promise<void>;
}

export function useCreativeNodeActions({
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
}: UseCreativeNodeActionsParams) {
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const selectedNodeRef = useRef(selectedNode);
  const workflowRef = useRef(workflow);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    selectedNodeRef.current = selectedNode;
  }, [selectedNode]);

  useEffect(() => {
    workflowRef.current = workflow;
  }, [workflow]);

  function updateNodeContent(nodeId: string, content: string, humanNote: string) {
    setNodes((current) => current.map((node) => node.id === nodeId
      ? { ...node, data: { ...node.data, content, humanNote, reviewStatus: "modified" } }
      : node));
    if (selectedNodeRef.current?.nodeId === nodeId) {
      setSelectedNode((current) => current?.nodeId === nodeId
        ? { ...current, content, humanNote, reviewStatus: "modified" }
        : current);
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
    if (selectedNodeRef.current?.nodeId === nodeId) {
      setSelectedNode((current) => current?.nodeId === nodeId
        ? { ...current, settings: { ...current.settings, ...settings } }
        : current);
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
    if (selectedNodeRef.current?.nodeId === nodeId) {
      setSelectedNode((current) => current?.nodeId === nodeId ? { ...current, ...patch } : current);
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

  async function insertNextNode(sourceId: string) {
    const source = nodesRef.current.find((node) => node.id === sourceId);
    if (!source) return;
    const localId = `${Date.now()}-next`;
    const data = createDramaNodeData(source.data.nodeType, nodesRef.current.length + 1);
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

    if (canvasId) {
      try {
        const updated = await addCanvasNode(canvasId, {
          node_type: source.data.nodeType,
          title: data.title,
          content: data.content,
          position: next.position,
        });
        const back = updated.nodes.find((node) => node.title === data.title);
        if (back) {
          setNodes((current) => current.map((node) => node.id === localId
            ? { ...node, id: back.node_id, data: { ...node.data, nodeId: back.node_id } }
            : node));
          setEdges((current) => current.map((edgeItem) => edgeItem.target === localId
            ? { ...edgeItem, id: `e-${sourceId}-${back.node_id}`, target: back.node_id }
            : edgeItem));
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
    const downstream = collectDownstream(sourceId, edgesRef.current);
    for (const id of downstream) {
      await runSingleStep(id);
    }
  }

  function saveNodeArtifactsToWorkspace(nodeId: string) {
    const node = nodesRef.current.find((item) => item.id === nodeId);
    if (!node) return;
    const count = node.data.artifacts.length;
    setError(count ? `已记录 ${count} 个产物到工作区资产（占位）` : "当前节点暂无产物可保存");
  }

  function reportError(error: unknown) {
    setError(error instanceof Error ? error.message : String(error));
  }

  function getNodeById(nodeId: string) {
    return nodesRef.current.find((item) => item.id === nodeId);
  }

  function patchNodeOnCanvas(nodeId: string, patch: Record<string, unknown>) {
    if (!canvasId) return;
    void patchCanvasNode(canvasId, nodeId, patch).catch(reportError);
  }

  async function runGenerateLikeAction(nodeId: string, fallback: () => Promise<void>) {
    const node = getNodeById(nodeId);
    if (node?.data.nodeType === "剪辑") {
      await runEditorForNode(nodeId);
      return;
    }
    if (node?.data.nodeType === "导出") {
      await runExportForNode(nodeId);
      return;
    }
    await fallback();
  }

  async function handleReviewNodeAction(nodeId: string, action: CanvasNodeAction) {
    if (action === "approve" || action === "reject") {
      const node = getNodeById(nodeId);
      const runId = workflowRef.current?.run_id ?? node?.data.workflowRunId;
      const stepId = node?.data.workflowStepId ?? nodeId;
      if (!runId) {
        setError("请先「运行画布」生成工作流再进行审核操作");
        return true;
      }
      const reviewStatus = action === "approve" ? "approved" : "rejected";
      try {
        const view = action === "approve"
          ? await approveWorkflow(runId, stepId)
          : await denyWorkflow(runId, stepId);
        applyWorkflowView(view);
        setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, reviewStatus } } : item));
      } catch (error: unknown) {
        reportError(error);
      }
      return true;
    }

    if (action === "request-review") {
      patchNodeData(nodeId, { reviewStatus: "review_required" });
      if (canvasId) {
        try {
          await requestCanvasReview(canvasId, nodeId);
        } catch (error: unknown) {
          reportError(error);
        }
      }
      return true;
    }

    if (action === "view-log") {
      setTimelineOpen(true);
      return true;
    }

    if (action === "view-history") {
      const node = getNodeById(nodeId);
      if (node) setError(`生成历史：${node.data.agentNote || "暂无 agent 备注"}`);
      return true;
    }

    return false;
  }

  async function handleExecutionNodeAction(nodeId: string, action: CanvasNodeAction) {
    if (action === "run") {
      await runGenerateLikeAction(nodeId, () => runSingleStep(nodeId));
      return true;
    }

    if (action === "generate") {
      await runGenerateLikeAction(nodeId, () => generateForNode(nodeId));
      return true;
    }

    if (action === "auto-execute") {
      await runGenerateLikeAction(nodeId, () => generateForNode(nodeId));
      return true;
    }

    if (action === "create-timeline" || action === "sync-upstream") {
      await runEditorForNode(nodeId);
      return true;
    }

    if (action === "agent-clip") {
      await runAgentClipForNode(nodeId);
      return true;
    }

    if (action === "render" || action === "export-draft") {
      await runExportForNode(nodeId);
      return true;
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
          return true;
        } catch (error: unknown) {
          reportError(error);
        }
      }
      const node = getNodeById(nodeId);
      if (node) patchNodeData(nodeId, { resourceEstimate: estimateResourceFor(node.data) });
      return true;
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
          return true;
        } catch (error: unknown) {
          reportError(error);
        }
      }
      const node = getNodeById(nodeId);
      if (node) patchNodeData(nodeId, { qualityReport: scoreNode(node.data) });
      return true;
    }

    if (action === "auto-fix") {
      if (canvasId) {
        try {
          const result = await autoFixCanvasNode(canvasId, nodeId);
          patchNodeData(nodeId, {
            settings: { ...(result.node.settings ?? {}) } as DramaNodeSettings,
            executionStatus: "pending",
          });
          return true;
        } catch (error: unknown) {
          reportError(error);
        }
      }
      const node = getNodeById(nodeId);
      if (!node) return true;
      const fixed = autoFixSettings(node.data);
      patchNodeData(nodeId, { settings: { ...(node.data.settings ?? {}), ...fixed }, executionStatus: "pending" });
      return true;
    }

    return false;
  }

  async function handleStructureNodeAction(nodeId: string, action: CanvasNodeAction) {
    if (action === "delete") {
      setNodes((current) => current.filter((node) => node.id !== nodeId));
      setEdges((current) => current.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
      setSelectedNode(null);
      if (canvasId) {
        void deleteCanvasNode(canvasId, nodeId).catch(reportError);
      }
      return true;
    }

    if (action === "duplicate") {
      const source = getNodeById(nodeId);
      if (!source) return true;
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
      if (canvasId) {
        try {
          const updated = await addCanvasNode(canvasId, {
            node_type: source.data.nodeType,
            title: data.title,
            content: source.data.content,
            position: { x: source.position.x + 40, y: source.position.y + 40 },
          });
          const back = updated.nodes.find((node) => node.title === data.title && node.node_type === source.data.nodeType);
          if (back) {
            setNodes((current) => current.map((node) => node.id === localId
              ? { ...node, id: back.node_id, data: { ...node.data, nodeId: back.node_id } }
              : node));
            if (source.data.settings && Object.keys(source.data.settings).length) {
              void patchCanvasNode(canvasId, back.node_id, {
                settings: source.data.settings as Record<string, unknown>,
              }).catch(() => {});
            }
          }
        } catch (error: unknown) {
          reportError(error);
        }
      }
      return true;
    }

    if (action === "insert-next") {
      await insertNextNode(nodeId);
      return true;
    }

    if (action === "rerun-downstream") {
      await rerunDownstream(nodeId);
      return true;
    }

    if (action === "lock") {
      patchNodeData(nodeId, { locked: true });
      patchNodeOnCanvas(nodeId, { locked: true });
      return true;
    }

    if (action === "unlock") {
      patchNodeData(nodeId, { locked: false });
      patchNodeOnCanvas(nodeId, { locked: false });
      return true;
    }

    if (action === "rename") {
      const node = getNodeById(nodeId);
      const next = window.prompt("重命名节点", node?.data.title ?? "");
      if (next && next.trim()) {
        const title = next.trim();
        patchNodeData(nodeId, { title });
        patchNodeOnCanvas(nodeId, { title });
      }
      return true;
    }

    if (action === "stop") {
      patchNodeData(nodeId, { executionStatus: "skipped", progress: undefined });
      return true;
    }

    if (action === "edit") {
      const node = getNodeById(nodeId);
      if (node) setSelectedNode(node.data);
      return true;
    }

    return false;
  }

  async function handleBrowserNodeAction(nodeId: string, action: CanvasNodeAction) {
    if (action === "save-asset") {
      saveNodeArtifactsToWorkspace(nodeId);
      return true;
    }

    if (action === "copy-prompt") {
      const node = getNodeById(nodeId);
      const prompt = node?.data.settings?.prompt ?? String(node?.data.content ?? "");
      if (navigator.clipboard) await navigator.clipboard.writeText(prompt).catch(() => {});
      return true;
    }

    if (action === "paste-prompt") {
      try {
        const text = await navigator.clipboard?.readText?.();
        if (text) updateNodeSettings(nodeId, { prompt: text });
      } catch {
        setError("无法读取剪贴板");
      }
      return true;
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
      const node = getNodeById(nodeId);
      if (node) setSelectedNode(node.data);
      return true;
    }

    if (action === "preview-artifact" || action === "download-artifact") {
      const node = getNodeById(nodeId);
      const artifact = node?.data.artifacts.find((art) => art.url);
      if (!artifact?.url) {
        setError("当前节点暂无可预览/下载的产物");
        return true;
      }
      if (action === "preview-artifact") window.open(artifact.url, "_blank");
      else {
        const anchor = document.createElement("a");
        anchor.href = artifact.url;
        anchor.download = artifact.title || "artifact";
        anchor.click();
      }
      return true;
    }

    if (action === "export-node-json") {
      const node = getNodeById(nodeId);
      if (!node) return true;
      const blob = new Blob([JSON.stringify(node.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${node.data.title || "node"}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      return true;
    }

    if (action === "import-node-json") {
      setError("从 JSON 导入节点功能即将开放");
      return true;
    }

    return false;
  }

  async function handleNodeAction(nodeId: string, action: CanvasNodeAction) {
    if (await handleReviewNodeAction(nodeId, action)) return;
    if (await handleExecutionNodeAction(nodeId, action)) return;
    if (await handleStructureNodeAction(nodeId, action)) return;
    if (await handleBrowserNodeAction(nodeId, action)) return;
  }

  return {
    updateNodeContent,
    updateNodeSettings,
    patchNodeData,
    handleNodeAction,
  };
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
