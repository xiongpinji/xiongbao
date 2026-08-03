import type { GoalBoardTask } from "../../api/spine";

interface ReleaseGroup {
  title: string;
  tasks: GoalBoardTask[];
}

export default function ReleasePane({
  title,
  groups,
  nextAction,
}: {
  title: string;
  groups: ReleaseGroup[];
  nextAction?: { kind: string; task_id?: string; reason?: string };
}) {
  const hasTasks = groups.some((group) => group.tasks.length > 0);

  return (
    <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="text-[13px] font-medium text-neutral-200">{title}</div>
      <div className="mt-3 space-y-4">
        {hasTasks ? (
          groups.map((group) =>
            group.tasks.length > 0 ? (
              <div key={group.title} className="space-y-2">
                <div className="text-[11px] font-medium text-neutral-600">{group.title}</div>
                <div className="space-y-2">
                  {group.tasks.map((task) => (
                    <article
                      key={task.task_id}
                      className="rounded-lg border border-white/[0.06] bg-white/[0.03] p-3 transition-colors hover:border-white/[0.12]"
                    >
                      <div className="text-[13px] font-medium text-neutral-200">{task.title}</div>
                      {task.detail ? <div className="mt-1 text-[11px] leading-5 text-neutral-500">{task.detail}</div> : null}
                    </article>
                  ))}
                </div>
              </div>
            ) : null,
          )
        ) : (
          <div className="rounded-lg border border-dashed border-white/[0.08] p-3 text-[12px] text-neutral-600">
            暂无发布项
          </div>
        )}
      </div>
      {nextAction ? (
        <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.03] p-3 text-[11px] text-neutral-400">
          下一步: {nextAction.kind}
          {nextAction.task_id ? ` · ${nextAction.task_id}` : ""}
          {nextAction.reason ? ` · ${nextAction.reason}` : ""}
        </div>
      ) : null}
    </section>
  );
}
