import { Activity, CheckCircle2, ChevronRight, Clock3, PanelRight, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import ConversationalCommand from "../chat/ConversationalCommand";
import { useShellDerivedState } from "../../shell/useShellStore";

function formatTime(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function statusLabel(status: string) {
  if (status === "running") return "运行中";
  if (status === "attention") return "待处理";
  return "就绪";
}

function statusTone(status: string) {
  if (status === "running") return "bg-amber-400";
  if (status === "attention") return "bg-red-400";
  return "bg-emerald-400";
}

export default function ShellContextPanel() {
  const { session, currentContext, recentTasks, activeTaskActivity } = useShellDerivedState();
  const relatedTasks = recentTasks.slice(0, 4);

  return (
    <aside className="hidden h-full w-[320px] shrink-0 flex-col border-l border-white/[0.07] bg-black/62 text-neutral-200 shadow-[inset_1px_0_0_rgba(255,255,255,0.03)] backdrop-blur-2xl xl:flex">
      <div className="flex h-12 items-center justify-between border-b border-white/[0.07] px-5">
        <div className="flex items-center gap-2">
          <PanelRight size={17} className="text-[#d6ad62]" />
          <span className="text-sm font-semibold text-white">Context</span>
        </div>
        <span className="rounded-full border border-[#8a6a32]/35 bg-[#171108]/70 px-2.5 py-1 text-xs font-medium text-[#f2d99c]">
          {statusLabel(currentContext?.status ?? "ready")}
        </span>
      </div>

      <div className="xagent-scrollbar min-h-0 flex-1 overflow-auto px-5 py-4">
        <section>
          <div className="mb-3 flex items-center justify-between text-xs uppercase tracking-[0.16em] text-neutral-500">
            <span>Session</span>
            <span>{formatTime(session.startedAt)}</span>
          </div>
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-white">{session.label}</div>
                <div className="mt-1 text-xs text-neutral-500">{session.currentProject}</div>
              </div>
              <span className="rounded-full bg-black/30 px-2 py-1 text-xs text-neutral-400">
                {formatTime(session.startedAt)}
              </span>
            </div>
            <div className="rounded-xl border border-white/[0.055] bg-black/22 p-3">
              <div className="text-xs text-neutral-500">Current file</div>
              <div className="mt-2 text-sm font-semibold text-white">{currentContext?.title ?? "工作区"}</div>
              <div className="mt-1 text-xs leading-5 text-neutral-500">{currentContext?.subtitle ?? "等待当前任务上下文"}</div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-neutral-400">
              <span className={`h-2 w-2 rounded-full ${statusTone(currentContext?.status ?? "ready")}`} />
              {statusLabel(currentContext?.status ?? "ready")}
            </div>
          </div>
        </section>

        <section className="mt-6">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
            <Sparkles size={13} className="text-[#d6ad62]" />
            Relevant sessions
          </div>
          <div className="space-y-2">
            {relatedTasks.map((task) => (
              <Link
                key={task.id}
                to={task.route}
                className="group block rounded-xl border border-transparent px-3 py-2.5 transition hover:border-white/[0.07] hover:bg-white/[0.04]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-white">{task.title}</div>
                    <div className="mt-1 line-clamp-2 text-xs leading-5 text-neutral-500">{task.subtitle}</div>
                  </div>
                  <ChevronRight size={15} className="mt-1 shrink-0 text-neutral-700 transition group-hover:text-[#f1c96f]" />
                </div>
              </Link>
            ))}
            {relatedTasks.length === 0 && (
              <div className="rounded-2xl border border-dashed border-white/[0.08] p-4 text-sm text-neutral-500">
                暂无相关会话。
              </div>
            )}
          </div>
        </section>

        <section className="mt-6">
          <ConversationalCommand
            compact
            title="上下文助手"
            context={currentContext?.title ?? "当前工作区"}
            placeholder="继续追问、总结当前页，或要求生成下一步..."
            initialAssistantMessage="我会根据当前页面上下文回答，并把你的意图转成下一步操作。"
            suggestions={["总结当前页", "下一步该做什么", "转成工作流任务"]}
          />
        </section>

        <section className="mt-6">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
            <Activity size={13} className="text-[#d6ad62]" />
            Past actions
          </div>
          <div className="space-y-3">
            {activeTaskActivity.map((item) => (
              <div key={item.id} className="flex gap-3 rounded-xl border border-white/[0.045] bg-black/16 p-3">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-400" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-medium text-white">
                    <span className="truncate">{item.title}</span>
                    <span className="shrink-0 text-xs text-neutral-600">{formatTime(item.timestamp)}</span>
                  </div>
                  <div className="mt-1 text-xs leading-5 text-neutral-500">{item.detail}</div>
                </div>
              </div>
            ))}
            {activeTaskActivity.length === 0 && (
              <div className="flex items-center justify-center gap-2 rounded-2xl border border-dashed border-white/[0.08] py-8 text-sm text-neutral-500">
                <Clock3 size={15} />
                No actions yet.
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}
