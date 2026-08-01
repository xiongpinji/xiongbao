/**
 * X-Agent TypeScript SDK —— 后端 API 的类型化客户端。
 *
 * 用法：
 *   const client = new XAgentClient({ baseUrl: "http://localhost:8000", token });
 *   const roles = await client.listRoles();
 *   const run = await client.runAgent({ goal: "你好" });
 */
import axios, { type AxiosInstance } from "axios";

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

export interface ScoredCandidate {
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

export interface WorkflowDraft {
  draft_id: string;
  brief: string;
  genre: string;
  platform: string;
  target_duration_seconds: number;
  status: string;
  nodes: Record<string, unknown>[];
}

export interface ClientOptions {
  baseUrl?: string;
  token?: string;
  timeoutMs?: number;
}

export class XAgentClient {
  private http: AxiosInstance;

  constructor(opts: ClientOptions = {}) {
    this.http = axios.create({
      baseURL: `${opts.baseUrl ?? "http://localhost:8000"}/api/v1`,
      timeout: opts.timeoutMs ?? 30_000,
    });
    if (opts.token) {
      this.http.defaults.headers.common.Authorization = `Bearer ${opts.token}`;
    }
  }

  setToken(token: string) {
    this.http.defaults.headers.common.Authorization = `Bearer ${token}`;
  }

  // ---- Auth ----
  async login(username: string, password: string, tenantId?: string) {
    const r = await this.http.post("/auth/login", {
      username,
      password,
      tenant_id: tenantId,
    });
    this.setToken(r.data.access_token);
    return r.data;
  }

  async me() {
    return (await this.http.get("/auth/me")).data;
  }

  // ---- Agents ----
  async listRoles(): Promise<AgentRole[]> {
    return (await this.http.get<{ roles: AgentRole[] }>("/agents/roles")).data.roles;
  }

  async runAgent(body: {
    goal: string;
    role?: string;
    capabilities?: string[];
  }): Promise<AgentRun> {
    return (await this.http.post<AgentRun>("/agents/run", body)).data;
  }

  // ---- Tasks (后台) ----
  async submitTask(body: { goal: string; role?: string }): Promise<{ task_id: string }> {
    return (await this.http.post("/tasks", body)).data;
  }

  async getTask(taskId: string) {
    return (await this.http.get(`/tasks/${taskId}`)).data;
  }

  // ---- Memory ----
  async writeMemory(items: { id: string; text: string }[]) {
    return (await this.http.post("/memory", { items })).data;
  }

  async searchMemory(query: string, topK = 5) {
    return (await this.http.post("/memory/search", { query, top_k: topK })).data;
  }

  // ---- Workflows ----
  async runWorkflow(body: {
    name: string;
    steps: { id: string; name: string; role?: string; goal: string }[];
  }): Promise<WorkflowView> {
    return (await this.http.post<WorkflowView>("/workflows", body)).data;
  }

  async listWorkflows(): Promise<WorkflowView[]> {
    return (await this.http.get<{ runs: WorkflowView[] }>("/workflows")).data.runs;
  }

  async approveWorkflow(runId: string, stepId: string) {
    return (await this.http.post(`/workflows/${runId}/approve/${stepId}`)).data;
  }

  // ---- Creative Studio ----
  async createDraft(body: {
    brief: string;
    genre?: string;
    platform?: string;
  }): Promise<WorkflowDraft> {
    return (await this.http.post<WorkflowDraft>("/creative-studio/workflow-draft", body)).data;
  }

  async reviewDraft(draftId: string, approved: boolean, comment = "") {
    return (
      await this.http.post(`/creative-studio/workflow-draft/${draftId}/review`, {
        approved,
        comment,
      })
    ).data;
  }

  // ---- Open Source Discovery ----
  async discover(query: string, limit = 10): Promise<ScoredCandidate[]> {
    return (await this.http.post<{ results: ScoredCandidate[] }>("/open-source/discover", {
      query,
      limit,
    })).data.results;
  }

  // ---- Billing ----
  async billingSummary() {
    return (await this.http.get("/billing/summary")).data;
  }

  // ---- Audit ----
  async auditVerify() {
    return (await this.http.get("/audit/verify")).data;
  }

  // ---- System ----
  async health() {
    return (await this.http.get("/health")).data;
  }

  async ready() {
    return (await this.http.get("/ready")).data;
  }

  // ---- Skills ----
  async listSkills() {
    return (await this.http.get("/skills")).data;
  }

  async skillStats() {
    return (await this.http.get("/skills/stats")).data;
  }

  // ---- Workflow Templates ----
  async listTemplates() {
    return (await this.http.get("/workflows/templates/list")).data;
  }

  async saveTemplate(body: { name: string; nodes: unknown[]; edges: unknown[]; template_id?: string }) {
    return (await this.http.post("/workflows/templates/save", body)).data;
  }

  async loadTemplate(templateId: string) {
    return (await this.http.get(`/workflows/templates/${templateId}`)).data;
  }

  async deleteTemplate(templateId: string) {
    return (await this.http.delete(`/workflows/templates/${templateId}`)).data;
  }

  // ---- MCP ----
  async mcpServers() {
    return (await this.http.get("/mcp/servers")).data;
  }

  // ---- Streaming (SSE) ----
  async *streamRun(body: { goal: string; mode?: string; strategy?: string }): AsyncGenerator<{ event: string; data: unknown }> {
    const resp = await fetch(`${this.http.defaults.baseURL}/stream/agents/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(this.http.defaults.headers.common.Authorization
          ? { Authorization: this.http.defaults.headers.common.Authorization as string }
          : {}),
      },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`Stream failed: ${resp.status}`);
    const reader = resp.body?.getReader();
    if (!reader) throw new Error("No response body");
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const parsed = JSON.parse(line.slice(6));
            yield parsed;
          } catch { /* skip malformed */ }
        }
      }
    }
  }

  // ---- Tenants ----
  async tenantInfo() {
    return (await this.http.get("/tenants/info")).data;
  }

  async listUsers() {
    return (await this.http.get("/tenants/users")).data;
  }

  async createApiKey(body: { name: string; scopes?: string[] }) {
    return (await this.http.post("/tenants/api-keys", body)).data;
  }
}
