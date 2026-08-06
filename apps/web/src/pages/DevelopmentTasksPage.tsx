import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitPullRequest, RefreshCw } from "lucide-react";
import { useState } from "react";
import {
  getDevelopmentTask,
  getDevelopmentTaskActions,
  getDevelopmentTaskPatch,
  listDevelopmentTasks,
  mutateDevelopmentTask,
  type DevelopmentTaskAction,
  type DevelopmentTaskStatus,
} from "../api/developmentTasks";
import { formatDateTime } from "../lib/time";

const STATUS_LABELS: Record<DevelopmentTaskStatus, string> = {
  running: "运行中",
  awaiting_review: "待审查",
  approved: "已批准",
  applied: "已应用",
  rejected: "已拒绝",
  conflict: "存在冲突",
  expired: "已过期",
  failed: "失败",
  timeout: "超时",
  cancelled: "已取消",
};

const ACTION_LABELS: Record<DevelopmentTaskAction, string> = {
  approve: "批准",
  reject: "拒绝并清理",
  apply: "应用到目标分支",
  cancel: "取消运行",
};

function shortCommit(value: string) {
  return value ? value.slice(0, 10) : "-";
}

export default function DevelopmentTasksPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const listQuery = useQuery({
    queryKey: ["development-tasks"],
    queryFn: () => listDevelopmentTasks(),
    refetchInterval: 10_000,
  });
  const activeId = selectedId ?? listQuery.data?.[0]?.task_id ?? null;
  const detailQuery = useQuery({
    queryKey: ["development-task", activeId],
    queryFn: () => getDevelopmentTask(activeId!),
    enabled: Boolean(activeId),
  });
  const patchQuery = useQuery({
    queryKey: ["development-task-patch", activeId],
    queryFn: () => getDevelopmentTaskPatch(activeId!),
    enabled: Boolean(activeId && detailQuery.data?.result_commit),
    retry: false,
  });
  const actionMutation = useMutation({
    mutationFn: ({ taskId, action }: { taskId: string; action: DevelopmentTaskAction }) =>
      mutateDevelopmentTask(taskId, action),
    onSuccess: (task, variables) => {
      setMessage(`${ACTION_LABELS[variables.action]}成功，当前状态：${STATUS_LABELS[task.status]}`);
      queryClient.invalidateQueries({ queryKey: ["development-tasks"] });
      queryClient.invalidateQueries({ queryKey: ["development-task", task.task_id] });
    },
    onError: (error) => {
      setMessage(`操作失败：${error instanceof Error ? error.message : "未知错误"}`);
    },
  });

  const task = detailQuery.data;
  const runAction = (action: DevelopmentTaskAction) => {
    if (!task) return;
    const confirmed = window.confirm(
      `${ACTION_LABELS[action]}开发任务 ${task.task_id}？\n此操作会记入审计链。`,
    );
    if (!confirmed) return;
    setMessage("");
    actionMutation.mutate({ taskId: task.task_id, action });
  };

  return (
    <div className="xagent-scrollbar h-full overflow-auto px-4 py-6 text-neutral-100 md:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-white/[0.07] pb-5">
          <div>
            <div className="text-xs font-medium tracking-wide text-neutral-500">Development Tasks</div>
            <h1 className="mt-2 text-2xl font-semibold text-white">开发任务</h1>
            <p className="mt-2 text-sm text-neutral-500">
              审查隔离 worktree 产物，明确批准后再应用到目标分支。
            </p>
          </div>
          <button
            type="button"
            onClick={() => listQuery.refetch()}
            className="flex items-center gap-2 rounded-md border border-white/[0.08] px-3 py-2 text-xs text-neutral-300 hover:bg-white/[0.05]"
          >
            <RefreshCw size={14} /> 刷新
          </button>
        </header>

        {message ? (
          <div className="rounded-md border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-neutral-300">
            {message}
          </div>
        ) : null}

        {listQuery.isError ? (
          <div className="rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
            开发任务加载失败。
          </div>
        ) : (
          <div className="grid min-h-[560px] gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
            <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <div className="mb-3 px-2 text-xs text-neutral-500">
                {listQuery.isLoading ? "加载中..." : `共 ${listQuery.data?.length ?? 0} 项`}
              </div>
              <div className="space-y-2">
                {listQuery.data?.map((item) => (
                  <button
                    key={item.task_id}
                    type="button"
                    onClick={() => setSelectedId(item.task_id)}
                    className={`w-full rounded-md border p-3 text-left transition ${
                      activeId === item.task_id
                        ? "border-white/[0.18] bg-white/[0.07]"
                        : "border-transparent hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-white">{item.goal}</span>
                      <span className="shrink-0 rounded bg-white/[0.07] px-2 py-0.5 text-[10px] text-neutral-300">
                        {STATUS_LABELS[item.status]}
                      </span>
                    </div>
                    <div className="mt-2 truncate font-mono text-[11px] text-neutral-500">
                      {item.task_id}
                    </div>
                    <div className="mt-1 text-[11px] text-neutral-600">
                      {formatDateTime(item.updated_at)}
                    </div>
                  </button>
                ))}
                {!listQuery.isLoading && listQuery.data?.length === 0 ? (
                  <div className="px-2 py-8 text-center text-sm text-neutral-500">暂无开发任务</div>
                ) : null}
              </div>
            </section>

            <section className="min-w-0 rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
              {!activeId ? (
                <div className="flex h-full items-center justify-center text-sm text-neutral-500">
                  选择一个开发任务查看详情
                </div>
              ) : detailQuery.isLoading ? (
                <div className="text-sm text-neutral-500">正在加载任务详情...</div>
              ) : detailQuery.isError || !task ? (
                <div className="text-sm text-red-300">开发任务详情加载失败。</div>
              ) : (
                <div className="space-y-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-lg font-semibold text-white">{task.goal}</h2>
                      <div className="mt-2 font-mono text-xs text-neutral-500">{task.task_id}</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {getDevelopmentTaskActions(task.status).map((action) => (
                        <button
                          key={action}
                          type="button"
                          disabled={actionMutation.isPending}
                          onClick={() => runAction(action)}
                          className="rounded-md border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-xs text-neutral-200 hover:bg-white/[0.1] disabled:opacity-50"
                        >
                          {ACTION_LABELS[action]}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
                    {[
                      ["状态", STATUS_LABELS[task.status]],
                      ["目标分支", task.target_branch],
                      ["Base", shortCommit(task.base_commit)],
                      ["结果 Commit", shortCommit(task.result_commit)],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-md border border-white/[0.06] p-3">
                        <div className="text-neutral-600">{label}</div>
                        <div className="mt-1 break-all font-mono text-neutral-300">{value}</div>
                      </div>
                    ))}
                  </div>

                  {task.error ? (
                    <div className="rounded-md border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-300">
                      {task.error}
                    </div>
                  ) : null}

                  {task.conflict_files.length > 0 ? (
                    <div>
                      <h3 className="mb-2 text-sm font-medium text-white">冲突文件</h3>
                      <ul className="space-y-1 font-mono text-xs text-amber-300">
                        {task.conflict_files.map((file) => <li key={file}>{file}</li>)}
                      </ul>
                    </div>
                  ) : null}

                  <div>
                    <h3 className="mb-2 text-sm font-medium text-white">Diff Stat</h3>
                    <pre className="xagent-scrollbar overflow-auto rounded-md border border-white/[0.06] bg-black/30 p-3 text-xs text-neutral-400">
                      {task.diff_stat || "暂无变更统计"}
                    </pre>
                  </div>

                  <div>
                    <h3 className="mb-2 text-sm font-medium text-white">测试摘要</h3>
                    <pre className="xagent-scrollbar overflow-auto rounded-md border border-white/[0.06] bg-black/30 p-3 text-xs text-neutral-400">
                      {JSON.stringify(task.test_summary, null, 2)}
                    </pre>
                  </div>

                  <div>
                    <h3 className="mb-2 flex items-center gap-2 text-sm font-medium text-white">
                      <GitPullRequest size={15} /> 完整 Patch
                    </h3>
                    <pre className="xagent-scrollbar max-h-[520px] overflow-auto whitespace-pre rounded-md border border-white/[0.06] bg-black/40 p-4 font-mono text-xs leading-5 text-neutral-300">
                      {patchQuery.isLoading
                        ? "正在加载 patch..."
                        : patchQuery.isError
                          ? "Patch 暂不可用"
                          : patchQuery.data || "暂无 patch"}
                    </pre>
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
