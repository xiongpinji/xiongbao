import { api } from "./client";

export interface GoalBoardGoal {
  goal_id?: string;
  title: string;
  phase: string;
  status: string;
  auto_advance?: boolean;
  auto_execute?: boolean;
}

export interface GoalBoardTask {
  task_id: string;
  title: string;
  detail?: string;
  status?: string;
  run_id?: string;
  blocker_reason?: string;
}

export interface GoalBoardNextAction {
  kind: string;
  task_id?: string;
  reason?: string;
}

export interface GoalBoardSnapshot {
  goal: GoalBoardGoal;
  columns: Record<string, GoalBoardTask[]>;
  next_action?: GoalBoardNextAction;
  initiatives?: Array<{
    initiative_id: string;
    title: string;
    status?: string;
    priority?: string;
  }>;
  unknown_status_tasks?: GoalBoardTask[];
}

export async function getGoalBoard(goalId: string) {
  const response = await api.get<GoalBoardSnapshot>(`/spine/goals/${encodeURIComponent(goalId)}/board`);
  return response.data;
}

// ─── P4 操作入口（治理视图） ───

export async function createGoal(input: { title: string; description?: string }) {
  const response = await api.post<{ goal: GoalBoardGoal }>("/spine/goals", input);
  return response.data;
}

export async function setAutoAdvance(
  goalId: string,
  input: { enabled: boolean; auto_execute?: boolean; max_retries?: number },
) {
  const response = await api.post(`/spine/goals/${encodeURIComponent(goalId)}/auto-advance`, input);
  return response.data;
}

export async function reviewTask(
  goalId: string,
  taskId: string,
  input: { diff: string },
) {
  const response = await api.post(
    `/spine/goals/${encodeURIComponent(goalId)}/tasks/${encodeURIComponent(taskId)}/review`,
    input,
  );
  return response.data;
}

export async function createRelease(
  goalId: string,
  input: { branch_name: string; commit_sha: string; pr_number?: string },
) {
  const response = await api.post(`/spine/goals/${encodeURIComponent(goalId)}/release`, input);
  return response.data;
}
