import type { GoalBoardTask } from "../../api/spine";

export default function TaskColumn({
  title,
  tasks,
}: {
  title: string;
  tasks: GoalBoardTask[];
}) {
  return (
    <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="text-[13px] font-medium text-neutral-200">{title}</div>
      <div className="mt-3 space-y-2">
        {tasks.length === 0 ? (
          <div className="rounded-lg border border-dashed border-white/[0.08] p-3 text-[12px] text-neutral-600">
            暂无任务
          </div>
        ) : (
          tasks.map((task) => (
            <article
              key={task.task_id}
              className="rounded-lg border border-white/[0.06] bg-white/[0.03] p-3 transition-colors hover:border-white/[0.12]"
            >
              <div className="text-[13px] font-medium text-neutral-200">{task.title}</div>
              {task.detail ? <div className="mt-1 text-[11px] leading-5 text-neutral-500">{task.detail}</div> : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}
