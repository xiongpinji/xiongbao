import { api } from "./client";

export type SchedulerJobAction = "run" | "pause" | "resume" | "delete";

export interface SchedulerJob {
  job_id: string;
  name: string;
  goal: string;
  role: string;
  cron_expr: string;
  interval_seconds: number;
  enabled: boolean;
  max_retries: number;
  retry_backoff_seconds: number;
  last_run: string | null;
  next_run: string;
  created_at: string;
  updated_at: string;
}

export interface SchedulerRun {
  run_id: string;
  job_id: string;
  scheduled_for: string;
  status: string;
  attempt: number;
  claimed_at: string | null;
  lease_expires_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  agent_run_id: string;
  result: string;
  error: string;
  next_retry_at: string | null;
  notification_status: string;
  notification_error: string;
}

export function getSchedulerJobActions(enabled: boolean): SchedulerJobAction[] {
  return enabled ? ["run", "pause", "delete"] : ["run", "resume", "delete"];
}

export function createJobConfirmation(jobId: string) {
  return { confirm_job_id: jobId };
}

export const listSchedulerJobs = () =>
  api.get<{ jobs: SchedulerJob[] }>("/scheduler/jobs").then((response) => response.data.jobs);

export const createSchedulerJob = (body: {
  name: string;
  goal: string;
  interval_seconds: number;
}) => api.post<SchedulerJob>("/scheduler/jobs", body).then((response) => response.data);

export const listSchedulerRuns = (jobId: string) =>
  api
    .get<{ runs: SchedulerRun[] }>(`/scheduler/jobs/${jobId}/runs`)
    .then((response) => response.data.runs);

export async function mutateSchedulerJob(job: SchedulerJob, action: SchedulerJobAction) {
  const confirmation = createJobConfirmation(job.job_id);
  if (action === "run") {
    return api.post(`/scheduler/jobs/${job.job_id}/run`, confirmation);
  }
  if (action === "delete") {
    return api.delete(`/scheduler/jobs/${job.job_id}`, { data: confirmation });
  }
  return api.patch(`/scheduler/jobs/${job.job_id}/toggle`, {
    ...confirmation,
    enabled: action === "resume",
  });
}
