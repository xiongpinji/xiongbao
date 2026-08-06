import { api } from "./client.ts";

export type CheckpointStatus =
  | "available"
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "rolled_back"
  | "rollback_failed"
  | string;

export interface CheckpointView {
  checkpoint_id: string;
  tenant_id: string;
  conversation_id: string;
  run_id: string;
  parent_checkpoint_id: string;
  step: number;
  status: CheckpointStatus;
  goal: string;
  changed_files: string[];
  resumed_run_id: string;
  rollback_source: string;
  rollback_commit: string;
  rollback_error: string;
  created_at: string;
  updated_at: string;
}

export interface CheckpointDetail extends CheckpointView {
  messages: Array<Record<string, unknown>>;
}

export const checkpointStatusLabel = (status: CheckpointStatus): string =>
  ({
    available: "可恢复",
    pending: "等待恢复",
    running: "恢复中",
    completed: "恢复完成",
    failed: "恢复失败",
    rolled_back: "已回滚",
    rollback_failed: "回滚失败",
  })[status] ?? status;

export const canResumeCheckpoint = (
  status: CheckpointStatus,
  resumedRunId = "",
): boolean => !resumedRunId && status !== "pending" && status !== "running";

export async function listCheckpoints(filters: {
  conversationId?: string;
  runId?: string;
}): Promise<CheckpointView[]> {
  const response = await api.get<{ checkpoints: CheckpointView[]; total: number }>(
    "/checkpoints",
    {
      params: {
        conversation_id: filters.conversationId || undefined,
        run_id: filters.runId || undefined,
      },
    },
  );
  return response.data.checkpoints;
}

export async function resumeCheckpoint(checkpointId: string) {
  const response = await api.post<{ accepted: boolean; checkpoint: CheckpointDetail }>(
    `/checkpoints/${encodeURIComponent(checkpointId)}/resume`,
    { confirm_checkpoint_id: checkpointId },
  );
  return response.data;
}

export async function rollbackCheckpoint(
  checkpointId: string,
  taskId: string,
  source: "commit" | "patch",
) {
  const response = await api.post<{
    rolled_back: boolean;
    checkpoint: CheckpointDetail;
  }>(`/checkpoints/${encodeURIComponent(checkpointId)}/rollback`, {
    confirm_checkpoint_id: checkpointId,
    task_id: taskId,
    source,
  });
  return response.data;
}
