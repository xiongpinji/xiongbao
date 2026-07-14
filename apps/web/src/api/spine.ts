import { api } from "./client";

export interface GoalBoardGoal {
  goal_id?: string;
  title: string;
  phase: string;
  status: string;
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
