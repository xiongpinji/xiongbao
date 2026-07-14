import type { GoalBoardSnapshot } from "../../api/spine";

function describeNextAction(nextAction: GoalBoardSnapshot["next_action"]) {
  if (!nextAction) {
    return null;
  }

  const parts = [nextAction.kind];
  if (nextAction.task_id) {
    parts.push(nextAction.task_id);
  }
  if (nextAction.reason) {
    parts.push(nextAction.reason);
  }
  return parts.join(" · ");
}

export default function GoalSummaryCard({ snapshot }: { snapshot: GoalBoardSnapshot }) {
  const nextActionText = describeNextAction(snapshot.next_action);

  return (
    <section className="xagent-surface p-6">
      <div className="text-xs uppercase tracking-[0.24em] text-neutral-500">Goal Board</div>
      <h1 className="mt-2 text-2xl font-semibold text-white">{snapshot.goal.title}</h1>
      <p className="mt-2 text-sm text-neutral-400">
        phase: {snapshot.goal.phase} · status: {snapshot.goal.status}
      </p>
      {nextActionText ? <div className="mt-4 text-sm text-neutral-200">next: {nextActionText}</div> : null}
    </section>
  );
}
