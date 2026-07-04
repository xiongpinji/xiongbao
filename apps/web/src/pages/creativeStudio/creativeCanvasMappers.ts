import type { Edge, Node } from "reactflow";
import type { CanvasNodeDTO } from "../../api/index.ts";
import type { DramaCanvasNodeData, DramaNodeType, ReviewStatus } from "../../components/canvas/canvasTypes.ts";

const ALLOWED_NODE_TYPES: DramaNodeType[] = ["需求分析", "梗概", "角色设定", "分镜", "关键帧", "视频", "配音", "字幕", "配乐", "剪辑", "导出"];
const UNKNOWN_NODE_TYPE_FALLBACK: DramaNodeType = "需求分析";

interface MapCanvasNodeToFlowNodeOptions {
  fallbackPosition?: { x: number; y: number };
  reviewStatus?: ReviewStatus;
}

function mapReviewStatus(status: string): ReviewStatus {
  switch (status) {
    case "approved":
    case "rejected":
    case "modified":
    case "review_required":
      return status;
    default:
      return "unreviewed";
  }
}

function hasValidCanvasPosition(position: CanvasNodeDTO["position"] | undefined): position is CanvasNodeDTO["position"] {
  return typeof position?.x === "number" && typeof position?.y === "number";
}

export function normalizeNodeType(value: string): DramaNodeType {
  if (ALLOWED_NODE_TYPES.includes(value as DramaNodeType)) {
    return value as DramaNodeType;
  }
  console.warn(
    `[creativeCanvasMappers] Unknown canvas node_type "${value}"; falling back to "${UNKNOWN_NODE_TYPE_FALLBACK}".`,
  );
  return UNKNOWN_NODE_TYPE_FALLBACK;
}

export function mapCanvasNodeToFlowNode(
  node: CanvasNodeDTO,
  index: number,
  options?: MapCanvasNodeToFlowNodeOptions,
): Node<DramaCanvasNodeData> {
  return {
    id: node.node_id,
    type: "dramaNode",
    position: hasValidCanvasPosition(node.position)
      ? node.position
      : (options?.fallbackPosition ?? { x: 120 + index * 280, y: 180 }),
    data: {
      nodeId: node.node_id,
      nodeType: normalizeNodeType(node.node_type),
      title: node.title,
      content: node.content,
      dependencies: node.dependencies ?? [],
      reviewStatus: options?.reviewStatus ?? mapReviewStatus(node.status),
      executionStatus: "pending",
      agentNote: node.agent_note,
      humanNote: node.human_note,
      artifacts: [],
      settings: (node.settings ?? {}) as DramaCanvasNodeData["settings"],
      locked: Boolean(node.locked),
    },
  };
}

export function mapDependenciesToEdges(nodes: CanvasNodeDTO[]): Edge[] {
  const nextEdges: Edge[] = [];
  for (const node of nodes) {
    for (const dependencyId of node.dependencies ?? []) {
      nextEdges.push({
        id: `e-${dependencyId}-${node.node_id}`,
        source: dependencyId,
        target: node.node_id,
        animated: true,
      });
    }
  }
  return nextEdges;
}
