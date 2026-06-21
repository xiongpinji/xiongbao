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

export const discoverOpenSource = (query: string, limit = 10) =>
  api
    .post<{ results: ScoredCandidateDTO[] }>("/open-source/discover", { query, limit })
    .then((r) => r.data.results);

export const writeMemory = (items: { id: string; text: string }[]) =>
  api.post("/memory", { items }).then((r) => r.data);

export const searchMemory = (query: string, top_k = 5) =>
  api.post("/memory/search", { query, top_k }).then((r) => r.data.hits);
