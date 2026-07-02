import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import RunConsole from "../components/runs/RunConsole.tsx";
import { getRunDetail } from "../api/runtime.ts";

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const query = useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => getRunDetail(runId ?? ""),
    enabled: Boolean(runId),
  });

  if (!runId) {
    return (
      <div className="flex min-h-full items-center justify-center bg-neutral-950 p-8 text-neutral-100">
        <div className="max-w-xl rounded-3xl border border-neutral-800 bg-neutral-900 p-8 shadow-2xl shadow-black/20">
          <div className="text-sm font-medium text-neutral-500">缺少参数</div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">未提供 runId</h1>
          <p className="mt-3 text-sm leading-6 text-neutral-400">请从任务、工作流或创意运行入口跳转到具体的运行详情页。</p>
          <Link
            to="/chat"
            className="mt-6 inline-flex rounded-xl bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-white active:scale-[0.98]"
          >
            返回对话
          </Link>
        </div>
      </div>
    );
  }

  if (query.isLoading) {
    return <div className="p-8 text-sm text-neutral-400">正在加载运行详情...</div>;
  }

  if (query.error || !query.data) {
    const message = query.error instanceof Error ? query.error.message : "运行详情加载失败";
    return (
      <div className="flex min-h-full items-center justify-center bg-neutral-950 p-8 text-neutral-100">
        <div className="max-w-xl rounded-3xl border border-red-900/60 bg-neutral-900 p-8 shadow-2xl shadow-black/20">
          <div className="text-sm font-medium text-red-300">加载失败</div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">无法读取运行 {runId}</h1>
          <p className="mt-3 text-sm leading-6 text-neutral-400">{message}</p>
          <div className="mt-6 flex gap-3">
            <button
              type="button"
              onClick={() => query.refetch()}
              className="rounded-xl bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-white active:scale-[0.98]"
            >
              重试
            </button>
            <Link
              to="/workflows"
              className="rounded-xl border border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-200 hover:border-neutral-500 hover:text-white"
            >
              打开工作流
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <RunConsole detail={query.data} />
      </div>
    </div>
  );
}
