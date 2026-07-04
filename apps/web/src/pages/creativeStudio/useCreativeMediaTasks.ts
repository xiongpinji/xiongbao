import { useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Node } from "reactflow";
import {
  batchGenerateCanvas,
  estimateCanvas,
  generateMedia,
  getMediaTask,
  scoreCanvas,
} from "../../api";
import type { DramaCanvasNodeData } from "../../components/canvas/canvasTypes";

interface UseCreativeMediaTasksParams {
  canvasId: string | null;
  nodes: Node<DramaCanvasNodeData>[];
  setNodes: Dispatch<SetStateAction<Node<DramaCanvasNodeData>[]>>;
  setError: Dispatch<SetStateAction<string | null>>;
}

export function useCreativeMediaTasks({
  canvasId,
  nodes,
  setNodes,
  setError,
}: UseCreativeMediaTasksParams) {
  const nodesRef = useRef(nodes);
  const taskPolls = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => () => {
    taskPolls.current.forEach((id) => window.clearInterval(id));
    taskPolls.current.clear();
  }, []);

  function markNodeFromTask(nodeId: string, taskId: string, status: string, outputs: string[] = []) {
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
            url: outputs[0] ?? artifact.url,
          } : artifact),
        },
      };
    }));
  }

  function startTaskPolling(nodeId: string, taskId: string) {
    if (taskPolls.current.has(taskId)) return;
    let attempt = 0;
    const maxAttempts = 40;
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

  async function generateForNode(nodeId: string) {
    const node = nodesRef.current.find((item) => item.id === nodeId);
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

  async function batchGenerateMedia() {
    if (!canvasId) {
      const targets = nodesRef.current.filter((node) => node.data.nodeType === "关键帧" || node.data.nodeType === "视频");
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
      setNodes((current) => current.map((node) => {
        const matched = result.results.find((entry) => entry.node_id === node.id);
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
      for (const entry of result.results) {
        if (entry.task_id) startTaskPolling(entry.node_id, entry.task_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function applyResourceEstimateAll() {
    if (!canvasId) {
      setNodes((current) => current.map((node) => ({
        ...node,
        data: { ...node.data, resourceEstimate: estimateResourceFor(node.data) },
      })));
      return;
    }
    try {
      const report = await estimateCanvas(canvasId);
      const byId = new Map(report.nodes.map((node) => [node.node_id, node]));
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
      setNodes((current) => current.map((node) => ({
        ...node,
        data: { ...node.data, qualityReport: scoreNode(node.data) },
      })));
      return;
    }
    try {
      const report = await scoreCanvas(canvasId);
      const byId = new Map(report.nodes.map((node) => [node.node_id, node]));
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

  return {
    startTaskPolling,
    batchGenerateMedia,
    applyResourceEstimateAll,
    applyQualityReportAll,
    generateForNode,
    estimateResourceFor,
    scoreNode,
  };
}

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
