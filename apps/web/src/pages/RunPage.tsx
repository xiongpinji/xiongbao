import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import RunConsole from "../components/runs/RunConsole.tsx";
import { getRunDetail } from "../api/runtime.ts";
import ConversationalCommand from "../components/chat/ConversationalCommand.tsx";

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const query = useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => getRunDetail(runId ?? ""),
    enabled: Boolean(runId),
  });

  if (!runId) {
    return (
      <RunFallback
        label="缺少参数"
        title="未提供 runId"
        description="请从任务、工作流或创意运行入口跳转到具体的运行详情页。"
      />
    );
  }

  if (query.isLoading) {
    return <div className="p-8 text-sm text-neutral-400">正在加载运行详情...</div>;
  }

  if (query.error || !query.data) {
    const message = query.error instanceof Error ? query.error.message : "运行详情加载失败";
    return (
      <RunFallback
        label="加载失败"
        title={`无法读取运行 ${runId}`}
        description={message}
        onRetry={() => query.refetch()}
      />
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

function RunFallback({
  label,
  title,
  description,
  onRetry,
}: {
  label: string;
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  return (
    <div className="xagent-scrollbar flex min-h-full items-center justify-center overflow-auto bg-transparent p-6 text-neutral-100">
      <div className="w-full max-w-3xl space-y-5">
        <header className="border-b border-white/[0.07] pb-5">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">{label}</div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">{title}</h1>
          <p className="mt-3 text-sm leading-6 text-neutral-500">{description}</p>
        </header>
        <ConversationalCommand
          title="运行恢复助手"
          context="运行详情不可用"
          placeholder="描述你想恢复的运行、来源任务，或直接要求回到工作流..."
          initialAssistantMessage="当前运行详情不可用。你可以让我回到对话、工作流，或重新尝试读取。"
          suggestions={["返回对话", "打开工作流", "重新读取运行"]}
          onSubmit={(value) => {
            if (value.includes("重新") && onRetry) {
              onRetry();
              return "已重新发起读取请求。";
            }
            if (value.includes("工作流")) {
              return "请使用下方入口进入工作流，选择对应任务后重新打开运行详情。";
            }
            return "建议先返回对话，重新描述目标或从最近任务里打开对应运行。";
          }}
        />
        <div className="flex flex-wrap gap-3">
          {onRetry && (
            <button type="button" onClick={onRetry} className="gold-button">
              重试
            </button>
          )}
          <Link to="/chat" className="gold-button">
            返回对话
          </Link>
          <Link to="/professional?mode=workflow" className="xagent-chip">
            打开工作流
          </Link>
        </div>
      </div>
    </div>
  );
}
