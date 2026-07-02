import { api } from "./client.ts";

export interface RuntimeTaskEvent {
  ts?: string;
  step_id?: string;
  kind?: string;
  tool?: string | null;
  content?: unknown;
  detail?: unknown;
}

export interface RuntimeTaskView {
  task_id: string;
  run_id: string;
  tenant_id?: string;
  owner_id?: string;
  kind: string;
  status: string;
  backend?: string;
  source?: string;
  intent_type?: string;
  route_source?: string;
  input?: Record<string, unknown>;
  result?: Record<string, unknown>;
  events?: RuntimeTaskEvent[];
  error?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at?: string | null;
}

export interface RuntimeWorkflowStep {
  id: string;
  name?: string;
  status?: string;
  depends_on?: string[];
  has_compensation?: boolean;
  has_approval?: boolean;
  error?: string | null;
}

export interface RuntimeWorkflowTimelineEvent {
  ts: string;
  step_id: string;
  kind: string;
  detail: unknown;
}

export interface RuntimeWorkflowView {
  run_id: string;
  spec_name?: string;
  tenant_id?: string;
  status?: string;
  steps?: RuntimeWorkflowStep[];
  timeline?: RuntimeWorkflowTimelineEvent[];
}

export interface RuntimeEvidenceRecord {
  evidence_id: string;
  tenant_id?: string;
  run_id?: string;
  task_id?: string | null;
  artifact_id?: string | null;
  kind: string;
  payload: unknown;
}

export interface RuntimeArtifactRecord {
  artifact_id: string;
  run_id?: string;
  task_id?: string | null;
  tenant_id?: string;
  kind: string;
  name: string;
  uri: string;
  content_type?: string;
  size_bytes?: number;
  checksum?: string;
  validation_summary?: Record<string, unknown>;
  delivery_summary?: Record<string, unknown>;
  lineage_summary?: Record<string, unknown>;
  preview_summary?: Record<string, unknown>;
}

export interface RuntimeDeliverySummary extends Record<string, unknown> {
  risks?: string[];
  replay?: Record<string, unknown> | null;
  resume?: Record<string, unknown> | null;
}

export interface RuntimeRelatedTask {
  task_id: string;
  run_id: string;
  owner_id?: string;
  kind: string;
  status: string;
  source?: string;
  preview_summary?: Record<string, unknown>;
  result?: Record<string, unknown>;
}

export interface RunDetailDTO {
  run_id: string;
  tenant_id: string;
  task: RuntimeTaskView | null;
  workflow: RuntimeWorkflowView | null;
  evidence: RuntimeEvidenceRecord[];
  artifacts: RuntimeArtifactRecord[];
  validation: Record<string, unknown>;
  delivery: RuntimeDeliverySummary;
  related_tasks: RuntimeRelatedTask[];
}

export interface RunTimelineEntry extends RuntimeWorkflowTimelineEvent {
  source: "workflow" | "task";
}

export interface RunDetail extends RunDetailDTO {
  timeline: RunTimelineEntry[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function normalizeWorkflowTimelineEntry(event: unknown, fallbackStepId: string): RunTimelineEntry {
  const record = isRecord(event) ? event : {};
  return {
    ts: typeof record.ts === "string" ? record.ts : "",
    step_id: typeof record.step_id === "string" ? record.step_id : fallbackStepId,
    kind: typeof record.kind === "string" ? record.kind : "event",
    detail: record.detail ?? {},
    source: "workflow",
  };
}

function normalizeTaskTimelineEntry(event: unknown, fallbackStepId: string): RunTimelineEntry {
  const record = isRecord(event) ? event : {};
  return {
    ts: typeof record.ts === "string" ? record.ts : "",
    step_id: typeof record.step_id === "string" ? record.step_id : fallbackStepId,
    kind: typeof record.kind === "string" ? record.kind : "event",
    detail: record.detail ?? record.content ?? record,
    source: "task",
  };
}

function compareTimelineEntries(
  left: { entry: RunTimelineEntry; index: number },
  right: { entry: RunTimelineEntry; index: number },
): number {
  const leftHasTimestamp = left.entry.ts.trim().length > 0;
  const rightHasTimestamp = right.entry.ts.trim().length > 0;

  if (leftHasTimestamp && rightHasTimestamp) {
    const leftTime = Date.parse(left.entry.ts);
    const rightTime = Date.parse(right.entry.ts);
    const leftValid = Number.isFinite(leftTime);
    const rightValid = Number.isFinite(rightTime);

    if (leftValid && rightValid && leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    if (leftValid !== rightValid) {
      return leftValid ? -1 : 1;
    }
  } else if (leftHasTimestamp !== rightHasTimestamp) {
    return leftHasTimestamp ? -1 : 1;
  }

  return left.index - right.index;
}

export function normalizeRunTimeline(detail: Partial<RunDetailDTO>): RunTimelineEntry[] {
  const merged: Array<{ entry: RunTimelineEntry; index: number }> = [];
  let index = 0;

  const workflowTimeline = Array.isArray(detail.workflow?.timeline) ? detail.workflow.timeline : [];
  for (const event of workflowTimeline) {
    merged.push({ entry: normalizeWorkflowTimelineEntry(event, `workflow-step-${index + 1}`), index });
    index += 1;
  }

  const taskResult = isRecord(detail.task?.result) ? detail.task.result : {};
  const taskTimeline = Array.isArray(taskResult.timeline) ? taskResult.timeline : [];
  for (const event of taskTimeline) {
    merged.push({ entry: normalizeTaskTimelineEntry(event, `task-step-${index + 1}`), index });
    index += 1;
  }

  const taskEvents = Array.isArray(detail.task?.events) ? detail.task.events : [];
  for (const event of taskEvents) {
    merged.push({ entry: normalizeTaskTimelineEntry(event, `task-event-${index + 1}`), index });
    index += 1;
  }

  return merged.sort(compareTimelineEntries).map((item) => item.entry);
}

function normalizeTask(task: RuntimeTaskView | null | undefined): RuntimeTaskView | null {
  if (!task) {
    return null;
  }
  return {
    ...task,
    input: normalizeRecord(task.input),
    result: normalizeRecord(task.result),
    events: Array.isArray(task.events) ? task.events : [],
  };
}

export function normalizeRunDetail(detail: Partial<RunDetailDTO>): RunDetail {
  return {
    run_id: typeof detail.run_id === "string" ? detail.run_id : "",
    tenant_id: typeof detail.tenant_id === "string" ? detail.tenant_id : "",
    task: normalizeTask(detail.task),
    workflow: detail.workflow ?? null,
    evidence: Array.isArray(detail.evidence) ? detail.evidence : [],
    artifacts: Array.isArray(detail.artifacts) ? detail.artifacts : [],
    validation: normalizeRecord(detail.validation),
    delivery: normalizeRecord(detail.delivery),
    related_tasks: Array.isArray(detail.related_tasks) ? detail.related_tasks : [],
    timeline: normalizeRunTimeline(detail),
  };
}

export async function getRunDetail(runId: string): Promise<RunDetail> {
  const response = await api.get<RunDetailDTO>(`/runs/${encodeURIComponent(runId)}`);
  return normalizeRunDetail(response.data);
}
