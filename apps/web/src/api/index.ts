import { api } from "./client";

// ---- 类型契约（与后端对齐）----
export interface AgentRole {
  name: string;
  description: string;
  capabilities: string[];
}

export interface StepEvent {
  kind: string;
  tool?: string | null;
  step: number;
  content: unknown;
}

export interface AgentRun {
  run_id: string;
  goal: string;
  role: string;
  tenant_id: string;
  final_answer: string;
  steps: number;
  events: StepEvent[];
}

export interface WorkflowView {
  run_id: string;
  spec_name: string;
  tenant_id: string;
  status: string;
  steps: {
    id: string;
    name: string;
    status: string;
    depends_on: string[];
    has_compensation: boolean;
    has_approval: boolean;
    error: string | null;
  }[];
  timeline: { ts: string; step_id: string; kind: string; detail: unknown }[];
}

export interface WorkflowDraftNode {
  node_id: string;
  node_type: string;
  agent_role: string;
  provider_kind: string;
  risk_level: string;
  estimated_cost: number;
  estimated_seconds: number;
  needs_review: boolean;
  params: Record<string, unknown>;
}

export interface WorkflowDraft {
  draft_id: string;
  brief: string;
  genre: string;
  platform: string;
  target_duration_seconds: number;
  status: string;
  tenant_id?: string;
  nodes: WorkflowDraftNode[];
}

export interface ScoredCandidateDTO {
  name: string;
  source: string;
  url: string;
  stars: number;
  license: string;
  score: number;
  breakdown: Record<string, number>;
  license_ok: boolean;
  notes: string;
}

// ---- API 调用 ----
export const listRoles = () =>
  api.get<{ roles: AgentRole[] }>("/agents/roles").then((r) => r.data.roles);

export const runAgent = (body: {
  goal: string;
  role?: string;
  capabilities?: string[];
}) => api.post<AgentRun>("/agents/run", body).then((r) => r.data);

export const runWorkflow = (body: {
  name: string;
  steps: { id: string; name: string; role?: string; goal: string }[];
}) => api.post<WorkflowView>("/workflows", body).then((r) => r.data);

export const listWorkflows = () =>
  api.get<{ runs: WorkflowView[] }>("/workflows").then((r) => r.data.runs);

export const createDraft = (body: {
  brief: string;
  genre?: string;
  platform?: string;
  target_duration_seconds?: number;
}) => api.post<WorkflowDraft>("/creative-studio/workflow-draft", body).then((r) => r.data);

export const reviewDraft = (id: string, approved: boolean, comment = "") =>
  api
    .post<WorkflowDraft>(`/creative-studio/workflow-draft/${id}/review`, { approved, comment })
    .then((r) => r.data);

export const listDrafts = () =>
  api.get<{ drafts: WorkflowDraft[] }>("/creative-studio/workflow-drafts").then((r) => r.data.drafts);

// 短剧全链路产出
export interface ShotProduct {
  shot_id: string;
  scene: string;
  image_prompt: string;
  video_prompt: string;
  image_outputs: string[];
  video_outputs: string[];
  image_error: string | null;
  video_error: string | null;
}

export interface ProductionResult {
  storyboard_id: string;
  run_id?: string;
  task_id?: string;
  title: string;
  brief: string;
  genre: string;
  platform: string;
  status: string;
  quality_passed: boolean;
  quality_gates: { name: string; passed: boolean; detail: string }[];
  shots: ShotProduct[];
  timeline_id?: string;
}

export const produce = (body: {
  brief: string;
  genre?: string;
  platform?: string;
  with_video?: boolean;
}) => api.post<ProductionResult>("/creative-studio/produce", body).then((r) => r.data);

export const listProductions = () =>
  api.get<{ productions: ProductionResult[] }>("/creative-studio/productions").then((r) => r.data.productions);

// 媒体模型列表
export interface MediaModel {
  model_id: string;
  name: string;
  kind: string;
  provider: string;
  modes: string[];
  description: string;
}

export const listMediaModels = (kind?: string) =>
  api
    .get<{ models: MediaModel[] }>("/creative-studio/media/models", { params: kind ? { kind } : {} })
    .then((r) => r.data.models);

export interface MediaGenerateResult {
  task_id?: string;
  status?: string;
  outputs?: string[];
  provider?: string;
  error?: string | null;
}

export const generateMedia = (body: Record<string, unknown>) =>
  api.post<MediaGenerateResult>("/creative-studio/media/generate", body).then((r) => r.data);

export interface MediaTaskView {
  task_id: string;
  kind: "image" | "video" | "audio";
  provider: string;
  status: "pending" | "running" | "succeeded" | "failed";
  outputs: string[];
  error?: string | null;
}

export const getMediaTask = (taskId: string) =>
  api.get<MediaTaskView>(`/creative-studio/media/tasks/${taskId}`).then((r) => r.data);

// 制作画布
export interface CanvasNodeDTO {
  node_id: string;
  node_type: string;
  title: string;
  content: unknown;
  status: string;
  agent_note: string;
  human_note: string;
  position: { x: number; y: number };
  dependencies: string[];
  settings?: Record<string, unknown>;
  locked?: boolean;
}

export interface CanvasDTO {
  canvas_id: string;
  title: string;
  brief: string;
  nodes: CanvasNodeDTO[];
}

export const createCanvas = (body: { brief: string; title?: string }) =>
  api.post<CanvasDTO>("/canvas", body).then((r) => r.data);

export const addCanvasNode = (canvasId: string, body: Record<string, unknown>) =>
  api.post<CanvasDTO>(`/canvas/${canvasId}/nodes`, body).then((r) => r.data);

export const reviewCanvasNode = (canvasId: string, nodeId: string, body: Record<string, unknown>) =>
  api.post<CanvasDTO>(`/canvas/${canvasId}/nodes/${nodeId}/review`, body).then((r) => r.data);

export interface CanvasLayoutInput {
  nodes: { node_id: string; position: { x: number; y: number } }[];
  edges: { source: string; target: string }[];
}

export const saveCanvasLayout = (canvasId: string, body: CanvasLayoutInput) =>
  api.put<CanvasDTO>(`/canvas/${canvasId}/layout`, body).then((r) => r.data);

export interface CanvasRunResult {
  canvas_id: string;
  workflow_run_id: string;
  workflow: WorkflowView;
  node_step_map: Record<string, string>;
  canvas: CanvasDTO;
}

export const runCanvas = (canvasId: string) =>
  api.post<CanvasRunResult>(`/canvas/${canvasId}/run`, {}).then((r) => r.data);

export interface CanvasRunStepResult {
  canvas_id: string;
  node_id: string;
  workflow_run_id: string;
  workflow: WorkflowView;
  canvas: CanvasDTO;
}

export const runCanvasStep = (canvasId: string, nodeId: string) =>
  api.post<CanvasRunStepResult>(`/canvas/${canvasId}/run/${nodeId}`, {}).then((r) => r.data);

export const approveWorkflow = (runId: string, stepId: string) =>
  api.post<WorkflowView>(`/workflows/${runId}/approve/${stepId}`, {}).then((r) => r.data);

export const denyWorkflow = (runId: string, stepId: string) =>
  api.post<WorkflowView>(`/workflows/${runId}/deny/${stepId}`, {}).then((r) => r.data);

// 视频剪辑
export interface EditorClip {
  id: string;
  track_type: string;
  source_url: string;
  timeline_start: number;
  timeline_end: number;
  text: string;
  duration: number;
}

export interface EditorTimeline {
  id: string;
  name: string;
  width: number;
  height: number;
  fps: number;
  total_duration: number;
  clips: EditorClip[];
  transitions: { id: string; clip_id: string; type: string; duration: number }[];
}

export const createTimeline = (body: { name?: string; width?: number; height?: number }) =>
  api.post<EditorTimeline>("/creative-studio/editor/timelines", body).then((r) => r.data);

export const listTimelines = () =>
  api.get<{ timelines: EditorTimeline[] }>("/creative-studio/editor/timelines").then((r) => r.data.timelines);

export const getTimeline = (id: string) =>
  api.get<EditorTimeline>(`/creative-studio/editor/timelines/${id}`).then((r) => r.data);

export const addClip = (tlId: string, body: Record<string, unknown>) =>
  api.post<EditorTimeline>(`/creative-studio/editor/timelines/${tlId}/clips`, body).then((r) => r.data);

export const removeClip = (tlId: string, clipId: string) =>
  api.delete<EditorTimeline>(`/creative-studio/editor/timelines/${tlId}/clips/${clipId}`).then((r) => r.data);

export const addTransition = (tlId: string, body: { clip_id: string; type: string; duration: number }) =>
  api.post<EditorTimeline>(`/creative-studio/editor/timelines/${tlId}/transitions`, body).then((r) => r.data);

export const renderTimeline = (tlId: string) =>
  api.post(`/creative-studio/editor/timelines/${tlId}/render`, {}).then((r) => r.data);

export const exportDraft = (tlId: string) =>
  api.post(`/creative-studio/editor/timelines/${tlId}/export-draft`, {}).then((r) => r.data);

export const agentClip = (body: Record<string, unknown>) =>
  api.post("/creative-studio/editor/agent-clip", body).then((r) => r.data);

export interface SystemCapabilities {
  tenant: string;
  tools: { name: string; description: string; kind: string }[];
  mcp_servers: { name: string; kind: string; endpoint: string; enabled: boolean }[];
  commands: { name: string; description: string }[];
  code_preview: { default_theme: string; tab_size: number; diff_mode: string };
  onboarding: string[];
}

export const getSystemCapabilities = () =>
  api.get<SystemCapabilities>("/system/capabilities").then((r) => r.data);

export const discoverOpenSource = (query: string, limit = 10) =>
  api
    .post<{ results: ScoredCandidateDTO[] }>("/open-source/discover", { query, limit })
    .then((r) => r.data.results);

export const writeMemory = (items: { id: string; text: string }[]) =>
  api.post("/memory", { items }).then((r) => r.data);

export const searchMemory = (query: string, top_k = 5) =>
  api.post("/memory/search", { query, top_k }).then((r) => r.data.hits);

// ---------------------------------------------------------------------------
// Canvas 扩展接口：节点 PATCH / 资源估算 / 质量评估 / 自动修复 / 剧本解析
//                批量生成 / 导入导出 / 请求审核
// ---------------------------------------------------------------------------

export interface CanvasNodePatchPayload {
  title?: string;
  content?: unknown;
  status?: string;
  human_note?: string;
  agent_note?: string;
  settings?: Record<string, unknown>;
  locked?: boolean;
  position?: { x: number; y: number };
  node_type?: string;
}

export const patchCanvasNode = (
  canvasId: string,
  nodeId: string,
  body: CanvasNodePatchPayload,
) =>
  api
    .patch<{ canvas: CanvasDTO; node: CanvasNodeDTO }>(
      `/canvas/${canvasId}/nodes/${nodeId}`,
      body,
    )
    .then((r) => r.data);

export const deleteCanvasNode = (canvasId: string, nodeId: string) =>
  api.delete<CanvasDTO>(`/canvas/${canvasId}/nodes/${nodeId}`).then((r) => r.data);

export interface CanvasResourceEstimate {
  nodes: {
    node_id: string;
    node_type: string;
    vram_mb: number;
    time_seconds: number;
    difficulty: "low" | "medium" | "high";
  }[];
  peak_vram_mb?: number;
  total_time_seconds?: number;
}

export const estimateCanvas = (canvasId: string, node_ids?: string[]) =>
  api
    .post<CanvasResourceEstimate>(`/canvas/${canvasId}/estimate`, node_ids ? { node_ids } : {})
    .then((r) => r.data);

export interface CanvasQualityReport {
  nodes: {
    node_id: string;
    node_type: string;
    overall: number;
    connectivity: number;
    completeness: number;
    parameters: number;
    security: number;
    executability: number;
    resource: number;
    issues: string[];
  }[];
  overall?: number;
  status_summary?: Record<string, number>;
}

export const scoreCanvas = (canvasId: string, node_ids?: string[]) =>
  api
    .post<CanvasQualityReport>(`/canvas/${canvasId}/quality`, node_ids ? { node_ids } : {})
    .then((r) => r.data);

export const autoFixCanvasNode = (canvasId: string, nodeId: string) =>
  api
    .post<{ patch: Record<string, unknown>; node: CanvasNodeDTO; canvas: CanvasDTO }>(
      `/canvas/${canvasId}/nodes/${nodeId}/auto-fix`,
      {},
    )
    .then((r) => r.data);

export const requestCanvasReview = (canvasId: string, nodeId: string) =>
  api.post<CanvasDTO>(`/canvas/${canvasId}/nodes/${nodeId}/request-review`, {}).then((r) => r.data);

export interface CanvasScriptParseInput {
  script?: string;
  auto_link?: boolean;
  keep_existing?: boolean;
}

export const parseCanvasScript = (canvasId: string, body: CanvasScriptParseInput = {}) =>
  api
    .post<{ created: CanvasNodeDTO[]; canvas: CanvasDTO }>(
      `/canvas/${canvasId}/script/parse`,
      body,
    )
    .then((r) => r.data);

export interface CanvasBatchGenerateResult {
  results: { node_id: string; task_id?: string; status?: string; provider?: string; error?: string }[];
  canvas: CanvasDTO;
}

export const batchGenerateCanvas = (canvasId: string, nodeTypes?: string[]) =>
  api
    .post<CanvasBatchGenerateResult>(`/canvas/${canvasId}/batch-generate`, {
      node_types: nodeTypes ?? ["关键帧", "视频"],
    })
    .then((r) => r.data);

export const exportCanvas = (canvasId: string) =>
  api.get<CanvasDTO & { edges: { source: string; target: string }[]; version: number }>(
    `/canvas/${canvasId}/export`,
  ).then((r) => r.data);

export const importCanvas = (body: {
  title?: string;
  brief?: string;
  nodes: Record<string, unknown>[];
  edges?: { source: string; target: string }[];
}) => api.post<CanvasDTO>(`/canvas/import`, body).then((r) => r.data);
