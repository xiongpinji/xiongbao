import { useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Node } from "reactflow";
import {
  addClip,
  addTransition,
  agentClip,
  createTimeline,
  exportDraft,
  getTimeline,
  renderTimeline,
  type EditorTimeline,
} from "../../api";
import type { DramaArtifact, DramaCanvasNodeData } from "../../components/canvas/canvasTypes";

interface UseCreativeEditorBridgeParams {
  brief: string;
  nodes: Node<DramaCanvasNodeData>[];
  editorTimeline: EditorTimeline | null;
  setEditorTimeline: Dispatch<SetStateAction<EditorTimeline | null>>;
  setNodes: Dispatch<SetStateAction<Node<DramaCanvasNodeData>[]>>;
  setError: Dispatch<SetStateAction<string | null>>;
}

export function useCreativeEditorBridge({
  brief,
  nodes,
  editorTimeline,
  setEditorTimeline,
  setNodes,
  setError,
}: UseCreativeEditorBridgeParams) {
  const briefRef = useRef(brief);
  const nodesRef = useRef(nodes);
  const editorTimelineRef = useRef(editorTimeline);

  useEffect(() => {
    briefRef.current = brief;
  }, [brief]);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    editorTimelineRef.current = editorTimeline;
  }, [editorTimeline]);

  async function runEditorForNode(nodeId: string) {
    setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "running" } } : item));
    try {
      const videoArtifacts = collectArtifacts(nodesRef.current, "video");
      const subtitleArtifacts = collectArtifacts(nodesRef.current, "subtitle");
      const audioArtifacts = collectArtifacts(nodesRef.current, "audio");

      const timeline = editorTimelineRef.current ?? await createTimeline({ name: briefRef.current.slice(0, 24) || "短剧时间线" });
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
      for (const clipId of clipIdsForTransition.slice(1)) {
        try {
          updated = await addTransition(timeline.id, { clip_id: clipId, type: "fade", duration: 0.5 });
        } catch {
          // 单个转场失败不影响整体
        }
      }
      editorTimelineRef.current = updated;
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

  async function runExportForNode(nodeId: string) {
    const currentTimeline = editorTimelineRef.current;
    if (!currentTimeline) {
      setError("先在剪辑节点创建时间线后再导出");
      return;
    }
    setNodes((current) => current.map((item) => item.id === nodeId ? { ...item, data: { ...item.data, executionStatus: "running" } } : item));
    try {
      const renderResult = await renderTimeline(currentTimeline.id) as { output_url?: string };
      const draftResult = await exportDraft(currentTimeline.id) as { draft_path?: string };
      setNodes((current) => current.map((item) => item.id === nodeId ? {
        ...item,
        data: {
          ...item.data,
          executionStatus: "succeeded",
          artifacts: [
            ...item.data.artifacts,
            ...(renderResult?.output_url
              ? [{ id: `${currentTimeline.id}-render`, kind: "video" as const, title: "渲染成片", url: renderResult.output_url, status: "succeeded" as const }]
              : []),
            ...(draftResult?.draft_path
              ? [{ id: `${currentTimeline.id}-draft`, kind: "draft" as const, title: "剪映草稿", url: draftResult.draft_path, status: "succeeded" as const }]
              : []),
          ],
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
      const instruction = briefRef.current.trim() || "请基于上游素材自动剪辑出 60 秒短剧";
      const result = (await agentClip({
        instruction,
        timeline_id: editorTimelineRef.current?.id,
      })) as { timeline_id?: string };
      const updatedTimeline = result.timeline_id ? await getTimeline(result.timeline_id) : null;
      if (updatedTimeline) {
        editorTimelineRef.current = updatedTimeline;
        setEditorTimeline(updatedTimeline);
      }
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

  return {
    runEditorForNode,
    runExportForNode,
    runAgentClipForNode,
  };
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
  artifacts: DramaArtifact[],
  timeline: EditorTimeline,
): DramaArtifact[] {
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
  artifacts: DramaArtifact[],
  timelineId: string,
): DramaArtifact[] {
  const next = artifacts.filter((artifact) => artifact.kind !== "timeline");
  next.push({
    id: timelineId,
    kind: "timeline",
    title: "智能体生成时间线",
    status: "succeeded",
  });
  return next;
}
