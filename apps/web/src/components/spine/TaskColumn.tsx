import type { GoalBoardTask } from "../../api/spine";

export default function TaskColumn({
  title,
  tasks,
}: {
  title: string;
  tasks: GoalBoardTask[];
}) {
  return (
    <section className="xagent-surface-subtle p-4">
      <div className="text-sm font-medium text-white">{title}</div>
      <div className="mt-3 space-y-2">
        {tasks.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/[0.08] bg-black/10 p-3 text-sm text-neutral-500">
            暂无任务
          </div>
        ) : (
          tasks.map((task) => (
            <article
              key={task.task_id}
              className="rounded-2xl border border-white/[0.08] bg-black/20 p-3 text-sm text-neutral-200"
            >
              <div className="font-medium text-white">{task.title}</div>
              {task.detail ? <div className="mt-1 text-xs leading-5 text-neutral-400">{task.detail}</div> : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}
