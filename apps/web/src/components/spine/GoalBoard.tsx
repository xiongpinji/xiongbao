import type { GoalBoardSnapshot } from "../../api/spine";
import GoalSummaryCard from "./GoalSummaryCard";
import ReleasePane from "./ReleasePane";
import TaskColumn from "./TaskColumn";

const RELEASE_COLUMNS = ["release_ready", "deploying", "verifying", "delivered", "recovery"] as const;

export default function GoalBoard({ snapshot }: { snapshot: GoalBoardSnapshot }) {
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
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)]">
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {taskColumns.map(([column, tasks]) => (
            <TaskColumn key={column} title={column} tasks={tasks} />
          ))}
        </div>
        <ReleasePane title="Release / Recovery" groups={releaseGroups} nextAction={releaseNextAction} />
      </div>
    </div>
  );
}
