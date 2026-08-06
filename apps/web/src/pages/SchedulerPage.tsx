import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createSchedulerJob,
  getSchedulerJobActions,
  listSchedulerJobs,
  listSchedulerRuns,
  mutateSchedulerJob,
  type SchedulerJob,
  type SchedulerJobAction,
} from "../api/scheduler";
import { formatDateTime } from "../lib/time";

const ACTION_LABELS: Record<SchedulerJobAction, string> = {
  run: "立即运行",
  pause: "暂停",
  resume: "恢复",
  delete: "删除",
};

export default function SchedulerPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [interval, setIntervalValue] = useState(3600);
  const [message, setMessage] = useState("");
  const jobsQuery = useQuery({
    queryKey: ["scheduler-jobs"],
    queryFn: listSchedulerJobs,
    refetchInterval: 10_000,
  });
  const activeId = selectedId ?? jobsQuery.data?.[0]?.job_id ?? null;
  const activeJob = jobsQuery.data?.find((job) => job.job_id === activeId) ?? null;
  const runsQuery = useQuery({
    queryKey: ["scheduler-runs", activeId],
    queryFn: () => listSchedulerRuns(activeId!),
    enabled: Boolean(activeId),
    refetchInterval: 10_000,
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["scheduler-jobs"] });
    queryClient.invalidateQueries({ queryKey: ["scheduler-runs"] });
  };
  const createMutation = useMutation({
    mutationFn: createSchedulerJob,
    onSuccess: (job) => {
      setSelectedId(job.job_id);
      setName("");
      setGoal("");
      setMessage("调度任务已创建");
      refresh();
    },
    onError: (error) => setMessage(`创建失败：${error instanceof Error ? error.message : "未知错误"}`),
  });
  const actionMutation = useMutation({
    mutationFn: ({ job, action }: { job: SchedulerJob; action: SchedulerJobAction }) =>
      mutateSchedulerJob(job, action),
    onSuccess: (_, variables) => {
      setMessage(`${ACTION_LABELS[variables.action]}请求已提交`);
      if (variables.action === "delete") setSelectedId(null);
      refresh();
    },
    onError: (error) => setMessage(`操作失败：${error instanceof Error ? error.message : "未知错误"}`),
  });

  const runAction = (job: SchedulerJob, action: SchedulerJobAction) => {
    if (!window.confirm(`${ACTION_LABELS[action]}调度任务 ${job.job_id}？`)) return;
    actionMutation.mutate({ job, action });
  };

  return (
    <div className="xagent-scrollbar h-full overflow-auto px-4 py-6 text-neutral-100 md:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="border-b border-white/[0.07] pb-5">
          <div className="text-xs text-neutral-500">Durable Scheduler</div>
          <h1 className="mt-2 text-2xl font-semibold">调度中心</h1>
          <p className="mt-2 text-sm text-neutral-500">查看数据库持久 Job、每次 attempt、租约与重试结果。</p>
        </header>

        <form
          className="grid gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 md:grid-cols-[180px_minmax(0,1fr)_140px_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate({ name: name.trim(), goal: goal.trim(), interval_seconds: interval });
          }}
        >
          <input className="field" placeholder="任务名称" value={name} onChange={(e) => setName(e.target.value)} />
          <input className="field" placeholder="Agent 目标" value={goal} onChange={(e) => setGoal(e.target.value)} />
          <input className="field" type="number" min={1} value={interval} onChange={(e) => setIntervalValue(Number(e.target.value))} />
          <button className="rounded-md bg-white px-4 py-2 text-sm text-black disabled:opacity-40" disabled={!name.trim() || !goal.trim() || createMutation.isPending}>创建</button>
        </form>

        {message ? <div className="rounded-md border border-white/[0.08] p-3 text-sm text-neutral-300">{message}</div> : null}

        <div className="grid min-h-[520px] gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
          <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
            <div className="mb-3 px-2 text-xs text-neutral-500">调度任务 · {jobsQuery.data?.length ?? 0}</div>
            {jobsQuery.data?.map((job) => (
              <button key={job.job_id} type="button" onClick={() => setSelectedId(job.job_id)} className={`mb-2 w-full rounded-md border p-3 text-left ${activeId === job.job_id ? "border-white/[0.18] bg-white/[0.07]" : "border-transparent hover:bg-white/[0.04]"}`}>
                <div className="flex justify-between gap-2 text-sm"><span className="truncate">{job.name}</span><span className="text-xs text-neutral-500">{job.enabled ? "已启用" : "已暂停"}</span></div>
                <div className="mt-2 truncate text-xs text-neutral-500">{job.goal}</div>
                <div className="mt-1 text-[11px] text-neutral-600">下次：{formatDateTime(job.next_run)}</div>
              </button>
            ))}
          </section>

          <section className="min-w-0 rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
            {!activeJob ? <div className="flex h-full items-center justify-center text-sm text-neutral-500">选择调度任务</div> : (
              <div className="space-y-5">
                <div className="flex flex-wrap justify-between gap-3">
                  <div><h2 className="text-lg font-semibold">{activeJob.name}</h2><div className="mt-1 font-mono text-xs text-neutral-500">{activeJob.job_id}</div></div>
                  <div className="flex gap-2">{getSchedulerJobActions(activeJob.enabled).map((action) => <button key={action} type="button" onClick={() => runAction(activeJob, action)} className="rounded-md border border-white/[0.1] px-3 py-2 text-xs hover:bg-white/[0.06]">{ACTION_LABELS[action]}</button>)}</div>
                </div>
                <div className="grid gap-3 text-xs sm:grid-cols-3">
                  <Info label="间隔" value={`${activeJob.interval_seconds}s`} />
                  <Info label="最大重试" value={String(activeJob.max_retries)} />
                  <Info label="退避基数" value={`${activeJob.retry_backoff_seconds}s`} />
                </div>
                <div>
                  <h3 className="mb-2 text-sm font-medium">运行历史</h3>
                  <div className="space-y-2">
                    {runsQuery.data?.map((run) => (
                      <div key={run.run_id} className="rounded-md border border-white/[0.06] p-3 text-xs">
                        <div className="flex flex-wrap justify-between gap-2"><span className="font-mono text-neutral-400">{run.run_id.slice(0, 12)} · attempt {run.attempt}</span><span>{run.status}</span></div>
                        <div className="mt-2 text-neutral-500">计划 {formatDateTime(run.scheduled_for)}{run.next_retry_at ? ` · 重试 ${formatDateTime(run.next_retry_at)}` : ""}</div>
                        {run.error ? <div className="mt-2 text-red-300">{run.error}</div> : null}
                        {run.result ? <div className="mt-2 whitespace-pre-wrap text-neutral-300">{run.result}</div> : null}
                      </div>
                    ))}
                    {!runsQuery.isLoading && runsQuery.data?.length === 0 ? <div className="py-8 text-center text-sm text-neutral-500">暂无运行历史</div> : null}
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="rounded-md border border-white/[0.06] p-3"><div className="text-neutral-600">{label}</div><div className="mt-1 font-mono text-neutral-300">{value}</div></div>;
}
