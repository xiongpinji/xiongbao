import { Activity, CheckCircle2, ChevronRight, Clock3, PanelRightClose, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import ConversationalCommand from "../chat/ConversationalCommand";
import { useShellDerivedState } from "../../shell/useShellStore";

function formatTime(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function statusTone(status: string) {
  if (status === "running") return "bg-amber-400";
  if (status === "attention") return "bg-red-400";
  return "bg-emerald-400";
}

export default function ShellContextPanel({ onClose }: { onClose: () => void }) {
  const { session, currentContext, recentTasks, activeTaskActivity } = useShellDerivedState();
  const relatedTasks = recentTasks.slice(0, 4);

  return (
    <aside className="flex h-full w-[300px] shrink-0 flex-col border-l border-white/[0.06] bg-[#111111]">
      <div className="flex h-11 items-center justify-between border-b border-white/[0.06] px-4">
        <span className="text-sm font-medium text-neutral-200">上下文</span>
        <button
          type="button"
          title="关闭面板"
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-500 transition hover:bg-white/[0.06] hover:text-white"
        >
          <PanelRightClose size={15} />
        </button>
      </div>

      <div className="xagent-scrollbar min-h-0 flex-1 overflow-auto px-4 py-4">
        {/* 当前会话 */}
        <section>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-neutral-600">
            会话 · {formatTime(session.startedAt)}
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
            <div className="text-sm font-medium text-white">{session.label}</div>
            <div className="mt-1 text-xs text-neutral-500">{session.currentProject}</div>
            <div className="mt-3 rounded-lg border border-white/[0.05] bg-black/20 p-2.5">
              <div className="text-[11px] text-neutral-600">当前上下文</div>
              <div className="mt-1 text-sm text-neutral-200">{currentContext?.title ?? "工作区"}</div>
              <div className="mt-0.5 text-xs text-neutral-500">{currentContext?.subtitle ?? "等待任务上下文"}</div>
            </div>
            <div className="mt-2.5 flex items-center gap-1.5 text-xs text-neutral-500">
              <span className={`h-1.5 w-1.5 rounded-full ${statusTone(currentContext?.status ?? "ready")}`} />
              {currentContext?.status === "running" ? "运行中" : "就绪"}
            </div>
          </div>
        </section>

        {/* 相关会话 */}
        <section className="mt-5">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-neutral-600">
            <Sparkles size={11} />
            相关会话
          </div>
          <div className="space-y-1">
            {relatedTasks.map((task) => (
              <Link
                key={task.id}
                to={task.route}
                className="group flex items-center gap-2 rounded-lg px-2.5 py-2 transition hover:bg-white/[0.04]"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-neutral-300 group-hover:text-white">{task.title}</div>
                  <div className="truncate text-xs text-neutral-600">{task.subtitle}</div>
                </div>
                <ChevronRight size={13} className="shrink-0 text-neutral-700 group-hover:text-neutral-400" />
              </Link>
            ))}
            {relatedTasks.length === 0 && (
              <div className="rounded-lg border border-dashed border-white/[0.06] px-3 py-4 text-center text-xs text-neutral-600">
                暂无相关会话
              </div>
            )}
          </div>
        </section>

        {/* 上下文助手 */}
        <section className="mt-5">
          <ConversationalCommand
            compact
            title="上下文助手"
            context={currentContext?.title ?? "当前工作区"}
            placeholder="追问或生成下一步..."
            initialAssistantMessage="我会根据当前页面上下文回答。"
            suggestions={["总结当前页", "下一步", "转成工作流"]}
          />
        </section>

        {/* 最近动作 */}
        <section className="mt-5">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-neutral-600">
            <Activity size={11} />
            最近动作
          </div>
          <div className="space-y-1.5">
            {activeTaskActivity.map((item) => (
              <div key={item.id} className="flex gap-2.5 rounded-lg border border-white/[0.04] bg-white/[0.015] p-2.5">
                <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-500" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm text-neutral-300">
                    <span className="truncate">{item.title}</span>
                    <span className="shrink-0 text-[10px] text-neutral-600">{formatTime(item.timestamp)}</span>
                  </div>
                  <div className="mt-0.5 text-xs text-neutral-600">{item.detail}</div>
                </div>
              </div>
            ))}
            {activeTaskActivity.length === 0 && (
              <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-white/[0.06] py-6 text-xs text-neutral-600">
                <Clock3 size={13} />
                暂无动作
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}
