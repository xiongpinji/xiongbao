import { api } from "./client";

export type DevelopmentTaskStatus =
  | "running"
  | "awaiting_review"
  | "approved"
  | "applied"
  | "rejected"
  | "conflict"
  | "expired"
  | "failed"
  | "timeout"
  | "cancelled";

export type DevelopmentTaskAction = "approve" | "reject" | "apply" | "cancel";

export interface DevelopmentTask {
  task_id: string;
  parent_run_id: string;
  sub_run_id: string;
  owner_id: string;
  goal: string;
  status: DevelopmentTaskStatus;
  base_commit: string;
  target_branch: string;
  work_branch: string;
  result_commit: string;
  applied_commit: string;
  diff_stat: string;
  test_summary: Record<string, unknown>;
  conflict_files: string[];
  error: string;
  reviewed_by: string;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
  applied_at: string | null;
  expires_at: string | null;
}

export function getDevelopmentTaskActions(
  status: DevelopmentTaskStatus,
): DevelopmentTaskAction[] {
  if (status === "running") return ["cancel"];
  if (status === "awaiting_review") return ["approve", "reject"];
  if (status === "approved") return ["apply", "reject"];
  if (status === "conflict") return ["reject"];
  return [];
}

export function createDevelopmentTaskConfirmation(taskId: string) {
  return { confirm_task_id: taskId };
}

export async function listDevelopmentTasks(status?: DevelopmentTaskStatus) {
  const response = await api.get<{ items: DevelopmentTask[] }>("/development-tasks", {
    params: status ? { status } : undefined,
  });
  return response.data.items;
}

export async function getDevelopmentTask(taskId: string) {
  const response = await api.get<DevelopmentTask>(`/development-tasks/${taskId}`);
  return response.data;
}

export async function getDevelopmentTaskPatch(taskId: string) {
  const response = await api.get<{ task_id: string; patch: string }>(
    `/development-tasks/${taskId}/patch`,
  );
  return response.data.patch;
}

export async function mutateDevelopmentTask(
  taskId: string,
  action: DevelopmentTaskAction,
) {
  const response = await api.post<DevelopmentTask>(
    `/development-tasks/${taskId}/${action}`,
    createDevelopmentTaskConfirmation(taskId),
  );
  return response.data;
}
