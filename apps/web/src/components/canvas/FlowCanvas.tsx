import { useCallback, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeTypes,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import CanvasContextMenu from "./CanvasContextMenu";
import CanvasNodeCard from "./CanvasNodeCard";
import CanvasToolbar from "./CanvasToolbar";
import type {
  CanvasGlobalAction,
  CanvasMenuState,
  CanvasNodeAction,
  DramaCanvasNodeData,
  DramaNodeType,
} from "./canvasTypes";
import { createDramaNodeData } from "./canvasTypes";

const nodeTypes: NodeTypes = {
  dramaNode: ({ data }) => <CanvasNodeCard data={data as DramaCanvasNodeData} />,
};

export default function FlowCanvas({
  nodes,
  edges,
  onChange,
  onSelectNode,
  onNodeAction,
  onCanvasAction,
}: {
  nodes: Node<DramaCanvasNodeData>[];
  edges: Edge[];
  onChange: (nodes: Node<DramaCanvasNodeData>[], edges: Edge[]) => void;
  onSelectNode: (node: DramaCanvasNodeData | null) => void;
  onNodeAction: (nodeId: string, action: CanvasNodeAction) => void;
  onCanvasAction?: (action: CanvasGlobalAction) => void;
}) {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner
        nodes={nodes}
        edges={edges}
        onChange={onChange}
        onSelectNode={onSelectNode}
        onNodeAction={onNodeAction}
        onCanvasAction={onCanvasAction}
      />
    </ReactFlowProvider>
  );
}

function FlowCanvasInner({
  nodes,
  edges,
  onChange,
  onSelectNode,
  onNodeAction,
  onCanvasAction,
}: {
  nodes: Node<DramaCanvasNodeData>[];
  edges: Edge[];
  onChange: (nodes: Node<DramaCanvasNodeData>[], edges: Edge[]) => void;
  onSelectNode: (node: DramaCanvasNodeData | null) => void;
  onNodeAction: (nodeId: string, action: CanvasNodeAction) => void;
  onCanvasAction?: (action: CanvasGlobalAction) => void;
}) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const reactFlow = useReactFlow<DramaCanvasNodeData>();
  const [menu, setMenu] = useState<CanvasMenuState | null>(null);
  const [menuFlowPosition, setMenuFlowPosition] = useState({ x: 120, y: 120 });

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const next = applyNodeChanges(changes, nodes) as Node<DramaCanvasNodeData>[];
      onChange(next, edges);
    },
    [nodes, edges, onChange],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const next = applyEdgeChanges(changes, edges);
      onChange(nodes, next);
    },
    [nodes, edges, onChange],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      const next = addEdge(
        { ...connection, markerEnd: { type: MarkerType.ArrowClosed }, animated: true },
        edges,
      );
      onChange(nodes, next);
    },
    [nodes, edges, onChange],
  );

  const addNode = useCallback(
    (nodeType: DramaNodeType) => {
      const data = createDramaNodeData(nodeType, nodes.length + 1);
      const next: Node<DramaCanvasNodeData>[] = [
        ...nodes,
        {
          id: data.nodeId,
          type: "dramaNode",
          position: menuFlowPosition,
          data,
        },
      ];
      onChange(next, edges);
      onSelectNode(data);
    },
    [nodes, edges, menuFlowPosition, onChange, onSelectNode],
  );

  const selectedNodeId = menu?.kind === "node" ? menu.nodeId : undefined;

  const selectedNodeData = useMemo<DramaCanvasNodeData | null>(() => {
    if (!selectedNodeId) return null;
    return nodes.find((node) => node.id === selectedNodeId)?.data ?? null;
  }, [nodes, selectedNodeId]);

  function handleCanvasContextMenu(event: React.MouseEvent) {
    event.preventDefault();
    const bounds = wrapperRef.current?.getBoundingClientRect();
    const position = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setMenuFlowPosition(position);
    setMenu({ kind: "canvas", x: event.clientX - (bounds?.left ?? 0), y: event.clientY - (bounds?.top ?? 0) });
  }

  function handleNodeContextMenu(event: React.MouseEvent, node: Node<DramaCanvasNodeData>) {
    event.preventDefault();
    event.stopPropagation();
    const bounds = wrapperRef.current?.getBoundingClientRect();
    setMenu({ kind: "node", nodeId: node.id, x: event.clientX - (bounds?.left ?? 0), y: event.clientY - (bounds?.top ?? 0) });
  }

  function handleNodeAction(action: CanvasNodeAction) {
    if (selectedNodeId) onNodeAction(selectedNodeId, action);
  }

  function handleCanvasAction(action: CanvasGlobalAction) {
    if (action === "fit-view") {
      reactFlow.fitView({ padding: 0.2, duration: 300 });
      return;
    }
    onCanvasAction?.(action);
  }

  function handleFitView() {
    reactFlow.fitView({ padding: 0.2, duration: 300 });
  }

  return (
    <div ref={wrapperRef} className="relative h-full w-full overflow-hidden bg-[#0f0f0f]" onContextMenu={handleCanvasContextMenu}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onNodeClick={(_, node) => onSelectNode(node.data)}
        onPaneClick={() => onSelectNode(null)}
        onNodeContextMenu={handleNodeContextMenu}
        fitView
        minZoom={0.12}
        maxZoom={2.5}
        panOnScroll
        defaultEdgeOptions={{ animated: true, markerEnd: { type: MarkerType.ArrowClosed } }}
      >
        <Background color="#262626" gap={24} size={1} />
        <Controls className="!border-neutral-800 !bg-neutral-900 !text-neutral-200" />
        <MiniMap className="!border-neutral-800 !bg-neutral-900" nodeColor="#525252" maskColor="rgba(0,0,0,0.45)" />
      </ReactFlow>
      <CanvasToolbar onAddNode={addNode} onFitView={handleFitView} onAutoLayout={() => handleCanvasAction("auto-layout")} />
      <CanvasContextMenu
        menu={menu}
        onClose={() => setMenu(null)}
        onAddNode={addNode}
        onNodeAction={handleNodeAction}
        onCanvasAction={handleCanvasAction}
        selectedNode={selectedNodeData}
      />
    </div>
  );
}
