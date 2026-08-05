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
    <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-6">
      <div className="text-[11px] font-medium text-neutral-600">Goal Board</div>
      <h1 className="mt-1.5 text-xl font-semibold tracking-tight text-neutral-100">{snapshot.goal.title}</h1>
      <p className="mt-2 text-[12px] text-neutral-500">
        阶段 {snapshot.goal.phase} · 状态 {snapshot.goal.status}
      </p>
      {nextActionText ? (
        <div className="mt-4 inline-flex items-center gap-2 rounded-md bg-white/[0.04] px-3 py-1.5 text-[12px] text-neutral-300">
          <span className="text-neutral-600">下一步</span>
          {nextActionText}
        </div>
      ) : null}
    </section>
  );
}
