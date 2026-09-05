import type { GoalBoardSnapshot } from "../../api/spine";
import type { AdvanceInput, ReleaseInput } from "./GoalActionBar";
import GoalActionBar from "./GoalActionBar";
import GoalSummaryCard from "./GoalSummaryCard";
import ReleasePane from "./ReleasePane";
import TaskColumn from "./TaskColumn";

const RELEASE_COLUMNS = ["release_ready", "deploying", "verifying", "delivered", "recovery"] as const;

export default function GoalBoard({
  snapshot,
  busy = false,
  actionMessage = "",
  onToggleAdvance,
  onCreateRelease,
  onReviewTask,
}: {
  snapshot: GoalBoardSnapshot;
  busy?: boolean;
  actionMessage?: string;
  onToggleAdvance?: (input: AdvanceInput) => void;
  onCreateRelease?: (input: ReleaseInput) => void;
  onReviewTask?: (goalId: string, taskId: string, diff: string) => void;
}) {
  const releaseGroups = RELEASE_COLUMNS.map((column) => ({
    title: column,
    tasks: snapshot.columns[column] ?? [],
  }));
  const releaseTaskIds = new Set(releaseGroups.flatMap((group) => group.tasks.map((task) => task.task_id)));
  const releaseNextAction =
    snapshot.next_action?.task_id && releaseTaskIds.has(snapshot.next_action.task_id)
      ? snapshot.next_action
      : undefined;
  const taskColumns = Object.entries(snapshot.columns).filter(([column]) => !RELEASE_COLUMNS.includes(column as (typeof RELEASE_COLUMNS)[number]));

  return (
    <div className="space-y-6">
      <GoalSummaryCard snapshot={snapshot} />
      {onToggleAdvance && onCreateRelease ? (
        <GoalActionBar
          snapshot={snapshot}
          busy={busy}
          message={actionMessage}
          onToggleAdvance={onToggleAdvance}
          onCreateRelease={onCreateRelease}
        />
      ) : null}
      <div className="space-y-4">
        <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
          {taskColumns.map(([column, tasks]) => (
            <TaskColumn
              key={column}
              title={column}
              tasks={tasks}
              goalId={snapshot.goal.goal_id}
              onReviewTask={onReviewTask}
            />
          ))}
        </div>
        <ReleasePane title="Release / Recovery" groups={releaseGroups} nextAction={releaseNextAction} />
      </div>
    </div>
  );
}
