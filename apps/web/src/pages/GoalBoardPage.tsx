import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createGoal, createRelease, getGoalBoard, reviewTask, setAutoAdvance } from "../api/spine";
import GoalBoard from "../components/spine/GoalBoard";

const DEFAULT_GOAL_ID = "phase1-xagent";

function CreateGoalForm({ onCreated }: { onCreated: (goalId: string) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const mutation = useMutation({
    mutationFn: () => createGoal({ title: title.trim(), description: description.trim() }),
    onSuccess: (data) => {
      if (data.goal.goal_id) onCreated(data.goal.goal_id);
    },
    onError: (err) => setMessage(`创建失败：${err instanceof Error ? err.message : "未知错误"}`),
  });
  return (
    <div className="mt-3 space-y-2">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Goal 标题"
        className="w-full rounded-md border border-white/[0.08] bg-transparent px-2 py-1.5 text-[12px] text-neutral-200 placeholder:text-neutral-600"
      />
      <input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="描述（可选）"
        className="w-full rounded-md border border-white/[0.08] bg-transparent px-2 py-1.5 text-[12px] text-neutral-200 placeholder:text-neutral-600"
      />
      <button
        type="button"
        disabled={mutation.isPending || title.trim().length === 0}
        onClick={() => mutation.mutate()}
        className="rounded-md bg-white/[0.08] px-3 py-1.5 text-[12px] text-neutral-200 transition-colors hover:bg-white/[0.12] disabled:opacity-50"
      >
        创建并分解任务
      </button>
      {message ? <div className="text-[12px] text-red-400">{message}</div> : null}
    </div>
  );
}

export default function GoalBoardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const goalId = useMemo(() => searchParams.get("goalId")?.trim() || DEFAULT_GOAL_ID, [searchParams]);

  const query = useQuery({
    queryKey: ["goal-board", goalId],
    queryFn: () => getGoalBoard(goalId),
    // 看板任务状态会变化，每 10s 静默刷新
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
  });

  // ─── P4 治理操作 mutations（页面级统一持有，子组件保持无 hooks 展示型） ───
  const [actionMessage, setActionMessage] = useState("");
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["goal-board"] });

  const advanceMutation = useMutation({
    mutationFn: (input: { enabled: boolean; auto_execute?: boolean }) =>
      setAutoAdvance(goalId, input),
    onSuccess: () => {
      setActionMessage("自动推进设置已更新");
      invalidate();
    },
    onError: (err) => setActionMessage(`设置失败：${err instanceof Error ? err.message : "未知错误"}`),
  });

  const releaseMutation = useMutation({
    mutationFn: (input: { branch_name: string; commit_sha: string; pr_number?: string }) =>
      createRelease(goalId, input),
    onSuccess: (data) => {
      setActionMessage(`release 已收口：${data.release_id}（交付 ${data.tasks_delivered} 个任务）`);
      invalidate();
    },
    onError: (err) => setActionMessage(`release 失败：${err instanceof Error ? err.message : "未知错误"}`),
  });

  const reviewMutation = useMutation({
    mutationFn: (input: { taskId: string; diff: string }) =>
      reviewTask(goalId, input.taskId, { diff: input.diff }),
    onSuccess: (data) => {
      setActionMessage(`复检完成：verdict=${data.verdict} → 任务 ${data.task_status}`);
      invalidate();
    },
    onError: (err) => setActionMessage(`复检失败：${err instanceof Error ? err.message : "未知错误"}`),
  });

  const actionBusy =
    advanceMutation.isPending || releaseMutation.isPending || reviewMutation.isPending;

  if (query.isLoading) {
    return <div className="p-8 text-neutral-400">正在加载 Goal Board...</div>;
  }

  if (query.isError) {
    const message = query.error instanceof Error ? query.error.message : "Goal Board 加载失败。";
    return (
      <div className="p-8 text-neutral-400">
        <div className="text-lg font-medium text-white">暂无 Goal 数据。</div>
        <div className="mt-2 text-sm text-neutral-500">当前 goalId：{goalId}</div>
        <div className="mt-2 text-sm text-neutral-500">{message}</div>
      </div>
    );
  }

  if (!query.data) {
    return <div className="p-8 text-neutral-400">暂无 Goal 数据。</div>;
  }

  return (
    <div className="p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={() => setShowCreate((v) => !v)}
            className="rounded-md border border-white/[0.08] px-3 py-1.5 text-[12px] text-neutral-300 transition-colors hover:border-white/[0.16]"
          >
            新建 Goal
          </button>
        </div>
        {showCreate ? (
          <div className="mb-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
            <CreateGoalForm
              onCreated={(id) => {
                setShowCreate(false);
                setSearchParams({ goalId: id });
                queryClient.invalidateQueries({ queryKey: ["goal-board"] });
              }}
            />
          </div>
        ) : null}
        <GoalBoard
          snapshot={query.data}
          busy={actionBusy}
          actionMessage={actionMessage}
          onToggleAdvance={(input) => advanceMutation.mutate(input)}
          onCreateRelease={(input) => releaseMutation.mutate(input)}
          onReviewTask={(_gid, taskId, diff) => reviewMutation.mutate({ taskId, diff })}
        />
      </div>
    </div>
  );
}
