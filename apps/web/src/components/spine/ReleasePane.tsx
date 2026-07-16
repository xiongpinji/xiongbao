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
    <section className="xagent-surface p-4">
      <div className="text-sm font-medium text-white">{title}</div>
      <div className="mt-3 space-y-4">
        {hasTasks ? (
          groups.map((group) =>
            group.tasks.length > 0 ? (
              <div key={group.title} className="space-y-2">
                <div className="text-xs uppercase tracking-[0.2em] text-neutral-500">{group.title}</div>
                <div className="space-y-2">
                  {group.tasks.map((task) => (
                    <article
                      key={task.task_id}
                      className="rounded-2xl border border-white/[0.08] bg-black/20 p-3 text-sm text-neutral-200"
                    >
                      <div className="font-medium text-white">{task.title}</div>
                      {task.detail ? <div className="mt-1 text-xs leading-5 text-neutral-400">{task.detail}</div> : null}
                    </article>
                  ))}
                </div>
              </div>
            ) : null,
          )
        ) : (
          <div className="rounded-2xl border border-dashed border-white/[0.08] bg-black/10 p-3 text-sm text-neutral-500">
            暂无发布项
          </div>
        )}
      </div>
      {nextAction ? (
        <div className="mt-4 rounded-2xl border border-white/[0.08] bg-black/20 p-3 text-xs text-neutral-300">
          release next: {nextAction.kind}
          {nextAction.task_id ? ` · ${nextAction.task_id}` : ""}
          {nextAction.reason ? ` · ${nextAction.reason}` : ""}
        </div>
      ) : null}
    </section>
  );
}
