import type { GoalBoardSnapshot } from "../../api/spine";
import GoalSummaryCard from "./GoalSummaryCard";
import TaskColumn from "./TaskColumn";

export default function GoalBoard({ snapshot }: { snapshot: GoalBoardSnapshot }) {
  return (
    <div className="space-y-6">
      <GoalSummaryCard snapshot={snapshot} />
      <div className="grid gap-4 lg:grid-cols-3 xl:grid-cols-4">
        {Object.entries(snapshot.columns).map(([column, tasks]) => (
          <TaskColumn key={column} title={column} tasks={tasks} />
        ))}
      </div>
    </div>
  );
}
