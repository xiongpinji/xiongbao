import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { getGoalBoard } from "../api/spine";
import GoalBoard from "../components/spine/GoalBoard";

const DEFAULT_GOAL_ID = "phase1-xagent";

export default function GoalBoardPage() {
  const [searchParams] = useSearchParams();
  const goalId = useMemo(() => searchParams.get("goalId")?.trim() || DEFAULT_GOAL_ID, [searchParams]);

  const query = useQuery({
    queryKey: ["goal-board", goalId],
    queryFn: () => getGoalBoard(goalId),
    // 看板任务状态会变化，每 10s 静默刷新
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
  });

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
        <GoalBoard snapshot={query.data} />
      </div>
    </div>
  );
}
