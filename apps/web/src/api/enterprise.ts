import { api } from "./client";

// ---- Billing 类型 ----
export interface BillingUsage {
  agent_runs: number;
  media_generations: number;
  tokens: number;
}

export interface BillingQuota {
  max_agent_runs: number;
  max_media_generations: number;
  max_tokens: number;
}

export interface BillingSummary {
  tenant_id: string;
  plan: "free" | "pro" | "enterprise";
  usage: BillingUsage;
  quota: BillingQuota;
  records_count: number;
}

export interface BillingRecord {
  ts: string;
  actor: string;
  action: string;
  cost: number;
  tokens: number;
  detail: Record<string, unknown>;
}

// ---- Audit 类型 ----
export interface AuditIntegrity {
  valid: boolean;
  first_broken_seq: number | null;
}

export interface AuditEvent {
  seq: number;
  ts: string;
  tenant_id: string;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
  hash: string;
  prev_hash: string;
}

export interface AuditListResponse {
  integrity: AuditIntegrity;
  events: AuditEvent[];
}

export interface AuditVerifyResponse {
  valid: boolean;
  first_broken_seq: number | null;
}

// ---- Billing API ----
export const getBillingSummary = () =>
  api.get<BillingSummary>("/billing/summary").then((r) => r.data);

export const setBillingPlan = (plan: "free" | "pro" | "enterprise") =>
  api.post<BillingSummary>("/billing/plan", { plan }).then((r) => r.data);

export const getBillingRecords = () =>
  api.get<{ records: BillingRecord[] }>("/billing/records").then((r) => r.data.records);

// ---- Audit API ----
export const getAuditEvents = () =>
  api.get<AuditListResponse>("/audit").then((r) => r.data);

export const verifyAuditChain = () =>
  api.get<AuditVerifyResponse>("/audit/verify").then((r) => r.data);

export const exportAuditJson = () =>
  api.get<string>("/audit/export", { responseType: "text" }).then((r) => r.data);
