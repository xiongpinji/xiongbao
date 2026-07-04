import type { Edge, Node } from "reactflow";
import {
  createDramaNodeData,
  type DramaCanvasNodeData,
  type DramaNodeType,
} from "../../components/canvas/canvasTypes.ts";

const STARTER_NODE_TYPES: DramaNodeType[] = ["需求分析", "梗概", "角色设定", "分镜"];

export function starterNodes(): Node<DramaCanvasNodeData>[] {
  return STARTER_NODE_TYPES.map((type, index) => {
    const data = createDramaNodeData(type, index + 1);
    return {
      id: data.nodeId,
      type: "dramaNode",
      position: { x: 120 + index * 300, y: 180 + (index % 2) * 140 },
      data,
    };
  });
}

export function starterEdges(nodes: Node<DramaCanvasNodeData>[]): Edge[] {
  return nodes.slice(1).map((node, index) => ({
    id: `e-${nodes[index].id}-${node.id}`,
    source: nodes[index].id,
    target: node.id,
    animated: true,
  }));
}
