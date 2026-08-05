import type { GoalBoardTask } from "../../api/spine";

function ReviewTrigger({
  goalId,
  taskId,
  onReviewTask,
}: {
  goalId: string;
  taskId: string;
  onReviewTask: (goalId: string, taskId: string, diff: string) => void;
}) {
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-[11px] text-sky-300">复检（code review）</summary>
      <form
        className="mt-2 space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          const diff = String(data.get("diff") ?? "").trim();
          if (diff) onReviewTask(goalId, taskId, diff);
        }}
      >
        <textarea
          name="diff"
          required
          placeholder="粘贴 unified diff 文本…"
          rows={5}
          className="w-full rounded-md border border-white/[0.08] bg-transparent p-2 font-mono text-[11px] text-neutral-200 placeholder:text-neutral-600"
        />
        <button
          type="submit"
          className="rounded-md bg-sky-500/20 px-2 py-1 text-[11px] text-sky-200 transition-colors hover:bg-sky-500/30"
        >
          提交复检
        </button>
      </form>
    </details>
  );
}

export default function TaskColumn({
  title,
  tasks,
  goalId,
  onReviewTask,
}: {
  title: string;
  tasks: GoalBoardTask[];
  goalId?: string;
  onReviewTask?: (goalId: string, taskId: string, diff: string) => void;
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
              {title === "review" && goalId && onReviewTask ? (
                <ReviewTrigger goalId={goalId} taskId={task.task_id} onReviewTask={onReviewTask} />
              ) : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}
