import { useEffect, useState, type ReactNode } from "react";
import { ArrowUp, Bot, CheckCircle2, FileText, Plus, UserRound } from "lucide-react";
import { Link } from "react-router-dom";
import { runAgent, type AgentRun } from "../api";
import { readAgentRunStream } from "../api/chatStream";
import { getToken } from "../api/client";
import { useShellActions, useShellStore } from "../shell/useShellStore";

export default function ChatPage() {
  const { appendActivity, syncRunTask } = useShellActions();
  const chatSessionVersion = useShellStore((state) => state.chatSessionVersion);
  const [goal, setGoal] = useState("");
  const [submittedGoal, setSubmittedGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setGoal("");
    setSubmittedGoal("");
    setLoading(false);
    setRun(null);
    setRunId(null);
    setStreamText("");
    setError(null);
  }, [chatSessionVersion]);

  async function submit() {
    const nextGoal = goal.trim();
    if (!nextGoal) return;
    setSubmittedGoal(nextGoal);
    setLoading(true);
    setError(null);
    setStreamText("");
    setRun(null);
    setRunId(null);
    appendActivity({
      taskId: "chat",
      title: "提交对话任务",
      detail: nextGoal,
      tone: "info",
    });

    // 优先走 SSE 流式，失败回退普通 run
    try {
      await runSSE(nextGoal);
    } catch {
      try {
        const nextRun = await runAgent({ goal: nextGoal });
        setError(null);
        setRun(nextRun);
        setRunId(nextRun.run_id);
        syncRunTask(nextRun.run_id, { source: "chat" });
        appendActivity({
          taskId: "chat",
          title: "Agent 已返回结果",
          detail: `运行 ${nextRun.run_id}`,
          tone: "success",
        });
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  async function runSSE(nextGoal: string) {
    const token = getToken();
    const resp = await fetch("/api/v1/stream/agents/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ goal: nextGoal }),
    });
    if (!resp.ok || !resp.body) throw new Error(`SSE ${resp.status}`);

    await readAgentRunStream(resp, {
      onFinalAnswer: setStreamText,
      onError: setError,
      onDone: (nextRunId) => {
        setRunId(nextRunId);
        syncRunTask(nextRunId, { source: "chat" });
        appendActivity({
          taskId: "chat",
          title: "流式任务完成",
          detail: `运行 ${nextRunId}`,
          tone: "success",
        });
      },
    });
  }

  return (
    <div className="xagent-page mx-auto flex h-full max-w-5xl flex-col px-4 py-4 md:px-6">
      <header className="flex shrink-0 items-center justify-between border-b border-white/[0.07] pb-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">AI 工作区</div>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-white">对话</h1>
          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-neutral-500">
            输入、输出和运行记录在同一条会话流里，像 Codex 一样连续推进任务。
          </p>
        </div>
        <Link
          to="/professional?mode=workflow"
          className="gold-button hidden md:inline-flex"
        >
          转为工作流
        </Link>
      </header>

      <section className="xagent-scrollbar min-h-0 flex-1 space-y-5 overflow-auto py-5">
        {!submittedGoal && !streamText && !run && !error && (
          <div className="xagent-chat-empty-state relative flex h-full min-h-[480px] flex-col items-center justify-center text-center">
            <div className="absolute h-[25rem] w-[25rem] rounded-full border border-[#d6ad62]/10 shadow-[0_0_150px_rgba(216,174,97,0.08)]" />
            <div className="absolute h-64 w-64 rounded-full border border-[#c92d2d]/10" />
            <div className="xagent-hero-mascot-frame relative">
              <img
                src="/assets/xiongbao-mascot.png"
                alt="熊宝儿"
                className="xagent-hero-mascot"
              />
            </div>
            <h2 className="relative text-3xl font-semibold tracking-tight text-white md:text-5xl">
              您好，我是 <span className="text-[#f1c96f]">熊宝儿</span>
            </h2>
            <p className="mt-3 text-lg font-medium text-neutral-100">今天想要构建什么？</p>
            <p className="mt-3 max-w-xl text-sm leading-6 text-neutral-500">
              直接描述目标，熊宝会把任务拆成可执行步骤，并在需要时进入工作流、短剧工厂或剪辑工作台。
            </p>
          </div>
        )}

        {submittedGoal && (
          <MessageRow icon={<UserRound size={18} />} title="你" align="right">
            {submittedGoal}
          </MessageRow>
        )}

        {(loading || streamText || run || error || runId) && (
          <MessageRow icon={<Bot size={18} />} title="熊宝">
            {loading && !streamText && !run && !error && (
              <div className="flex items-center gap-2 text-sm text-neutral-400">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[#d6ad62]" />
                正在分析任务并调用 Agent...
              </div>
            )}
            {error && <div className="text-sm leading-6 text-red-300">{error}</div>}
            {streamText && <div className="whitespace-pre-wrap text-sm leading-7 text-neutral-200">{streamText}</div>}
            {run && (
              <div className="space-y-4">
                <div className="whitespace-pre-wrap text-sm leading-7 text-neutral-200">{run.final_answer}</div>
                <details className="rounded-2xl border border-white/[0.07] bg-black/20 p-4">
                  <summary className="cursor-pointer text-sm font-medium text-neutral-300">
                    事件序列（{run.events.length}）
                  </summary>
                  <ol className="mt-3 space-y-2 text-xs text-neutral-500">
                    {run.events.map((event, index) => (
                      <li key={`${event.step}-${index}`} className="flex gap-2">
                        <span className="text-[#d6ad62]">[{event.step}]</span>
                        <span>{event.kind}{event.tool ? ` · ${event.tool}` : ""}</span>
                      </li>
                    ))}
                  </ol>
                </details>
              </div>
            )}
            {runId && (
              <Link
                to={`/runs/${encodeURIComponent(runId)}`}
                className="mt-4 inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.045] px-3 py-2 text-sm text-neutral-200 transition hover:border-[#d6ad62]/50 hover:text-white"
              >
                <FileText size={15} />
                查看运行详情
              </Link>
            )}
          </MessageRow>
        )}
      </section>

      <footer className="shrink-0 pb-2">
        <div className="xagent-command-shell xagent-sheen">
          <textarea
            className="block min-h-28 w-full resize-none rounded-t-[22px] border-0 bg-transparent px-5 py-4 text-sm leading-6 text-neutral-100 outline-none placeholder:text-neutral-600"
            placeholder="描述一个任务或提出一个问题..."
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                event.preventDefault();
                void submit();
              }
            }}
          />
          <div className="flex items-center justify-between border-t border-white/[0.08] px-4 py-3">
            <div className="flex items-center gap-2">
              <button className="xagent-chip inline-flex items-center gap-2 rounded-xl">
                <Plus size={15} />
                添加上下文
              </button>
              <button className="xagent-chip rounded-xl">
                Auto
              </button>
            </div>
            <button
              type="button"
              onClick={submit}
              disabled={loading || !goal.trim()}
              className="xagent-send-button h-11 w-11"
              title="运行 Agent"
            >
              {loading ? <CheckCircle2 size={18} className="animate-pulse" /> : <ArrowUp size={20} />}
            </button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap justify-center gap-2 text-sm text-neutral-400">
          {["写一个函数", "修复 Bug", "添加测试", "构建工作流", "生成分镜"].map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => setGoal(prompt)}
              className="xagent-chip"
            >
              {prompt}
            </button>
          ))}
        </div>
      </footer>
    </div>
  );
}

function MessageRow({
  icon,
  title,
  align = "left",
  children,
}: {
  icon: ReactNode;
  title: string;
  align?: "left" | "right";
  children: ReactNode;
}) {
  return (
    <div className={`flex gap-3 ${align === "right" ? "justify-end" : "justify-start"}`}>
      {align === "left" && <Avatar>{icon}</Avatar>}
      <div className={`max-w-[760px] ${align === "right" ? "items-end" : "items-start"} flex flex-col`}>
        <div className="mb-2 text-xs font-medium text-neutral-500">{title}</div>
        <div
          className={`rounded-[22px] border px-5 py-4 shadow-[0_18px_50px_rgba(0,0,0,0.25)] ${
            align === "right" ? "xagent-message-user" : "xagent-message-assistant"
          }`}
        >
          <div className="whitespace-pre-wrap text-sm leading-7">{children}</div>
        </div>
      </div>
      {align === "right" && <Avatar>{icon}</Avatar>}
    </div>
  );
}

function Avatar({ children }: { children: ReactNode }) {
  return (
    <div className="xagent-icon-tile mt-6 h-9 w-9 rounded-2xl">
      {children}
    </div>
  );
}
