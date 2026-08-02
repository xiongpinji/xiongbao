import { useEffect, useRef, useState, useCallback } from "react";
import {
  ArrowUp, Bot, Check, CheckCircle2, ChevronDown, ChevronRight, Code2, Copy,
  FileText, Globe, Loader2, Square, Terminal, UserRound, XCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { runAgent, type AgentRun } from "../api";
import { readAgentRunStream, type StepInfo, type TokenUsage } from "../api/chatStream";
import { getToken } from "../api/client";
import { useShellActions, useShellStore } from "../shell/useShellStore";
import { MarkdownRenderer, CollapsibleSection } from "../components/chat/MarkdownRenderer";
import ConversationSidebar from "../components/chat/ConversationSidebar";

/* ================================================================== */
/*  类型                                                               */
/* ================================================================== */

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  runId?: string;
  run?: AgentRun;
  steps?: StepInfo[];
  streaming?: boolean;
  timestamp?: number;  // 发送时间戳
}

/* ================================================================== */
/*  主页面                                                             */
/* ================================================================== */

export default function ChatPage() {
  const { appendActivity, syncRunTask } = useShellActions();
  const chatSessionVersion = useShellStore((s) => s.chatSessionVersion);
  const chatSessionKey = useShellStore((s) => s.chatSessionKey);

  const [goal, setGoal] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(
    () => localStorage.getItem("xagent_conversation_id")
  );
  const [streamingText, setStreamingText] = useState("");
  const [completedSegments, setCompletedSegments] = useState<string[]>([]);
  const [sidebarKey, setSidebarKey] = useState(0);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage | null>(null);
  const [execProgress, setExecProgress] = useState<{ percent: number; step: number; maxSteps: number } | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 持久化 conversationId
  useEffect(() => {
    if (conversationId) localStorage.setItem("xagent_conversation_id", conversationId);
    else localStorage.removeItem("xagent_conversation_id");
  }, [conversationId]);

  useEffect(() => {
    setGoal(""); setMessages([]); setLoading(false);
    setError(null); setConversationId(null); setSteps([]); setStreamingText("");
    setCompletedSegments([]);
  }, [chatSessionVersion, chatSessionKey]);

  // 智能滚动：仅在用户位于底部时自动滚动
  const isNearBottomRef = useRef(true);
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const threshold = 100; // 距离底部 100px 内视为“底部”
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  useEffect(() => {
    if (isNearBottomRef.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, loading, steps, streamingText]);

  // 页面加载时恢复当前会话消息
  useEffect(() => {
    if (!conversationId) return;
    const token = getToken();
    fetch(`/api/v1/stream/conversations/${conversationId}/messages`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.messages?.length) {
          setMessages(data.messages.map((m: { role: string; content: string }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
          })));
        }
      })
      .catch(() => {});
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // 切换会话：加载历史消息
  const handleSelectConversation = useCallback(async (id: string) => {
    setConversationId(id);
    setSteps([]);
    setStreamingText("");
    setError(null);
    setMessages([]);
    try {
      const token = getToken();
      const resp = await fetch(`/api/v1/stream/conversations/${id}/messages`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data?.messages?.length) {
          setMessages(data.messages.map((m: { role: string; content: string }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
          })));
        }
      }
    } catch { /* ignore */ }
  }, []);

  // 新对话
  const handleNewConversation = useCallback(() => {
    setConversationId(null);
    setMessages([]);
    setSteps([]);
    setStreamingText("");
    setError(null);
    setGoal("");
    setSidebarKey((k) => k + 1);
  }, []);

  // 停止当前 SSE 流
  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const submit = useCallback(async () => {
    const nextGoal = goal.trim();
    if (!nextGoal || loading) return;
    setGoal("");
    setError(null);
    setSteps([]);
    setStreamingText("");
    setCompletedSegments([]);
    setMessages((prev) => [...prev, { role: "user", content: nextGoal, timestamp: Date.now() }]);
    setLoading(true);
    appendActivity({ taskId: "chat", title: "提交任务", detail: nextGoal, tone: "info" });

    try {
      await runSSE(nextGoal);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setMessages((prev) => [...prev, { role: "assistant", content: "（已停止）" }]);
      } else {
        try {
          const nextRun = await runAgent({ goal: nextGoal });
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: nextRun.final_answer, runId: nextRun.run_id, run: nextRun, timestamp: Date.now() },
          ]);
          syncRunTask(nextRun.run_id, { source: "chat" });
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    } finally {
      setLoading(false);
      setStreamingText("");
      setCompletedSegments([]);
      abortRef.current = null;
    }
  }, [goal, loading, conversationId]);

  async function runSSE(nextGoal: string): Promise<void> {
    const token = getToken();
    const controller = new AbortController();
    abortRef.current = controller;

    const resp = await fetch("/api/v1/stream/agents/run", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ goal: nextGoal, conversation_id: conversationId || undefined }),
      signal: controller.signal,
    });
    if (!resp.ok || !resp.body) throw new Error(`SSE ${resp.status}`);

    let result = "";
    let sseRunId = "";
    const collectedSteps: StepInfo[] = [];
    let tokenBuf = "";
    const segments: string[] = [];

    await readAgentRunStream(resp, {
      onStarted: (convId) => setConversationId(convId),
      onToken: (t) => {
        tokenBuf += t;
        setStreamingText(tokenBuf);
      },
      onFinalAnswer: (text) => {
        result = text;
        if (!tokenBuf) setStreamingText(text);
      },
      onError: setError,
      onStep: (step) => {
        collectedSteps.push(step);
        setSteps([...collectedSteps]);
        if (step.kind === "tool_call") {
          if (tokenBuf.trim()) {
            segments.push(tokenBuf.trim());
            setCompletedSegments([...segments]);
          }
          tokenBuf = "";
          setStreamingText("");
        }
      },
      onDone: (nextRunId, usage) => {
        sseRunId = nextRunId;
        if (usage) setTokenUsage(usage);
        setExecProgress(null);
        syncRunTask(nextRunId, { source: "chat" });
        appendActivity({ taskId: "chat", title: "任务完成", detail: `运行 ${nextRunId}`, tone: "success" });
        // 浏览器通知：任务完成时提醒（需用户授权）
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification("X-Agent 任务完成", { body: `运行 ${nextRunId.slice(0, 8)}... 已完成`, icon: "🤖" });
        }
      },
      onProgress: (percent, step, maxSteps) => {
        setExecProgress({ percent, step, maxSteps });
      },
    });

    // 最终回答优先用 result，否则用累积的 segments + token
    let finalContent = result || [...segments, tokenBuf].filter(Boolean).join("\n\n");
    if (!finalContent && collectedSteps.length > 0) {
      const toolCallCount = collectedSteps.filter((s) => s.kind === "tool_call").length;
      finalContent = `任务已执行完成（共 ${toolCallCount} 次工具调用），但模型未生成文字总结。请尝试换一种方式提问。`;
    }
    if (sseRunId || finalContent) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: finalContent, runId: sseRunId, steps: [...collectedSteps], timestamp: Date.now() },
      ]);
    }
  }

  const isEmpty = messages.length === 0 && !loading && !error;

  return (
    <div className="flex h-full">
      {/* 对话历史侧栏 */}
      <ConversationSidebar
        key={sidebarKey}
        activeId={conversationId}
        onSelect={handleSelectConversation}
        onNew={handleNewConversation}
      />

      {/* 主聊天区 */}
      <div className="flex min-w-0 flex-1 flex-col">
      {/* 消息区 */}
      <div ref={scrollRef} onScroll={handleScroll} className="xagent-scrollbar min-h-0 flex-1 overflow-auto">
        {isEmpty ? (
          <EmptyState onPick={(t) => { setGoal(t); textareaRef.current?.focus(); }} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-1 px-4 py-6">
            {messages.map((msg, i) => (
              <MessageBlock key={i} msg={msg} />
            ))}

            {/* 实时执行状态 */}
            {loading && (
              <div className="py-4">
                {steps.length > 0 && <ToolExecutionPanel steps={steps} live />}
                <div className="mt-3 flex items-center gap-3 text-sm text-neutral-500">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/[0.05]">
                    <Loader2 size={14} className="animate-spin text-neutral-400" />
                  </div>
                  <ElapsedTimer />
                  <span className="text-neutral-600">·</span>
                  <CurrentActionText steps={steps} />
                </div>
                {/* 骨架屏加载效果：无步骤且无流式文本时显示 */}
                {steps.length === 0 && !streamingText && completedSegments.length === 0 && (
                  <div className="mt-4 space-y-2 animate-pulse">
                    <div className="h-3 w-3/4 bg-neutral-800 rounded" />
                    <div className="h-3 w-1/2 bg-neutral-800 rounded" />
                    <div className="h-3 w-2/3 bg-neutral-800 rounded" />
                  </div>
                )}
                {/* 流式文本预览（含已完成 segments） */}
                {(() => {
                  const displayText = [...completedSegments, streamingText].filter(Boolean).join("\n\n");
                  return displayText ? (
                    <div className="mt-3 rounded-2xl border border-white/[0.06] bg-white/[0.02] px-5 py-4">
                      <MarkdownRenderer content={displayText} />
                    </div>
                  ) : null;
                })()}
              </div>
            )}

            {error && (
              <div className="my-3 flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3">
                <XCircle size={16} className="mt-0.5 shrink-0 text-red-400" />
                <span className="text-sm text-red-400">{error}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="shrink-0 border-t border-white/[0.06] bg-[#111111] px-4 py-3">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-end gap-2 rounded-xl border border-white/[0.08] bg-[#1a1a1a] px-4 py-3 transition focus-within:border-white/[0.15]">
            <textarea
              ref={textareaRef}
              className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-sm leading-6 text-neutral-100 outline-none placeholder:text-neutral-600"
              placeholder="描述一个任务或提出一个问题..."
              rows={1}
              value={goal}
              onChange={(e) => {
                setGoal(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); }
              }}
            />
            {loading ? (
              <button
                type="button"
                onClick={handleStop}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/90 text-white transition hover:bg-red-400"
                title="停止生成"
              >
                <Square size={14} fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                onClick={submit}
                disabled={!goal.trim()}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-black transition hover:bg-neutral-200 disabled:opacity-30"
                title="发送 (Enter)"
              >
                <ArrowUp size={16} />
              </button>
            )}
          </div>
          <div className="mt-2 flex items-center justify-center gap-4 text-[11px] text-neutral-700">
            <span>Enter 发送</span>
            <span>Shift+Enter 换行</span>
            <span>支持代码执行 · 文件操作 · 网页抓取 · 图像生成</span>
            {tokenUsage && (
              <span className="text-neutral-500 tabular-nums" title={`Prompt: ${tokenUsage.promptTokens.toLocaleString()} | Completion: ${tokenUsage.completionTokens.toLocaleString()}`}>
                🔢 {(tokenUsage.promptTokens + tokenUsage.completionTokens).toLocaleString()} tokens
                <span className="text-neutral-600"> (↑{tokenUsage.promptTokens.toLocaleString()} ↓{tokenUsage.completionTokens.toLocaleString()})</span>
              </span>
            )}
            {execProgress && (
              <div className="flex items-center gap-2">
                <div className="w-24 h-1.5 bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-300"
                    style={{ width: `${execProgress.percent}%` }}
                  />
                </div>
                <span className="text-blue-400 text-xs tabular-nums">
                  {execProgress.step}/{execProgress.maxSteps}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  耗时计时器 + 当前动作状态                                          */
/* ================================================================== */

function ElapsedTimer() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const iv = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(iv);
  }, []);
  const mm = Math.floor(elapsed / 60);
  const ss = elapsed % 60;
  return (
    <span className="tabular-nums text-neutral-500">
      {mm > 0 ? `${mm}m ${ss}s` : `${ss}s`}
    </span>
  );
}

function CurrentActionText({ steps }: { steps: StepInfo[] }) {
  const lastToolCall = [...steps].reverse().find((s) => s.kind === "tool_call");
  const lastToolResult = [...steps].reverse().find((s) => s.kind === "tool_result");
  // 如果最后一个 tool_call 没有对应的 result，说明正在执行
  const isExecuting = lastToolCall && (!lastToolResult || steps.indexOf(lastToolResult) < steps.indexOf(lastToolCall));
  if (isExecuting && lastToolCall?.tool) {
    const label = TOOL_LABELS[lastToolCall.tool] || lastToolCall.tool;
    return <span className="text-blue-400/80">正在{label}...</span>;
  }
  if (steps.length > 0) {
    return <span className="text-neutral-500">正在整合结果...</span>;
  }
  return <span className="text-neutral-500">正在思考...</span>;
}

/* ================================================================== */
/*  空态                                                               */
/* ================================================================== */

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const suggestions = [
    { icon: <Code2 size={16} />, text: "写一个 Python 脚本计算斐波那契数列前 20 项并执行" },
    { icon: <Terminal size={16} />, text: "查看当前系统环境信息（Python版本、操作系统、目录）" },
    { icon: <Globe size={16} />, text: "抓取 Hacker News 首页标题并总结热点" },
    { icon: <FileText size={16} />, text: "创建一个 FastAPI 项目骨架（main.py + requirements.txt）" },
    { icon: <Code2 size={16} />, text: "分析当前项目的依赖关系并生成架构图" },
    { icon: <Terminal size={16} />, text: "运行测试并修复失败的用例" },
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center px-4">
      <div className="mb-10 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/[0.08] bg-white/[0.04]">
          <Bot size={26} className="text-neutral-400" />
        </div>
        <h1 className="text-xl font-semibold text-white">有什么可以帮你的？</h1>
        <p className="mt-2 text-sm text-neutral-500">
          描述目标，熊宝会规划步骤、调用工具、逐步执行并交付结果。
        </p>
      </div>
      <div className="grid w-full max-w-xl gap-2.5">
        {suggestions.map((s) => (
          <button
            key={s.text}
            type="button"
            onClick={() => onPick(s.text)}
            className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3.5 text-left text-sm text-neutral-400 transition hover:border-white/[0.12] hover:bg-white/[0.04] hover:text-neutral-200"
          >
            <span className="text-neutral-600">{s.icon}</span>
            {s.text}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ================================================================== */
/*  工具执行面板（Codex 风格）                                          */
/* ================================================================== */

const TOOL_ICONS: Record<string, string> = {
  python_exec: "🐍",
  shell_exec: "⚡",
  web_fetch: "🌐",
  file_write: "📝",
  file_read: "📖",
  file_list: "📂",
  file_edit: "✏️",
  git: "🔀",
  code_search: "🔍",
  memory_write: "🧠",
  memory_search: "🔎",
  skill_exec: "🚀",
};

/** 工具友好名称 */
const TOOL_LABELS: Record<string, string> = {
  python_exec: "执行 Python",
  shell_exec: "执行命令",
  web_fetch: "拓取网页",
  file_write: "写入文件",
  file_read: "读取文件",
  file_list: "列出目录",
  file_edit: "编辑文件",
  git: "Git 操作",
  code_search: "搜索代码",
  memory_write: "写入记忆",
  memory_search: "检索记忆",
};

function ToolExecutionPanel({ steps, live = false }: { steps: StepInfo[]; live?: boolean }) {
  // 将 steps 配对为 (call, result) 组
  const groups: { call: StepInfo; result?: StepInfo }[] = [];
  for (let i = 0; i < steps.length; i++) {
    if (steps[i].kind === "tool_call") {
      const result = steps[i + 1]?.kind === "tool_result" ? steps[i + 1] : undefined;
      groups.push({ call: steps[i], result });
      if (result) i++;
    }
  }

  const successCount = groups.filter((g) => g.result && !String(g.result.content ?? "").startsWith("[错误]")).length;
  const errorCount = groups.filter((g) => g.result && String(g.result.content ?? "").startsWith("[错误]")).length;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-xs font-medium text-neutral-500">
        <Terminal size={12} />
        <span>执行过程</span>
        {live && <Loader2 size={11} className="animate-spin text-neutral-600" />}
        <span className="text-neutral-700">
          ({groups.length} 步{successCount > 0 && <span className="text-green-500/70"> ✓{successCount}</span>}{errorCount > 0 && <span className="text-red-400/70"> ✗{errorCount}</span>})
        </span>
      </div>
      {groups.map((g, i) => (
        <ToolCard key={i} call={g.call} result={g.result} index={i + 1} />
      ))}
    </div>
  );
}

function ToolCard({ call, result, index }: { call: StepInfo; result?: StepInfo; index: number }) {
  const [open, setOpen] = useState(false);
  const toolName = call.tool || "tool";
  const icon = TOOL_ICONS[toolName] || "🔧";
  const label = TOOL_LABELS[toolName] || toolName;
  const args = call.content != null
    ? (typeof call.content === "string" ? call.content : JSON.stringify(call.content, null, 2))
    : "";
  const output = result?.content != null
    ? (typeof result.content === "string" ? result.content : JSON.stringify(result.content, null, 2))
    : "";
  const isError = output.startsWith("[错误]") || output.includes("失败");
  const isRunning = !result;

  // file_edit 的 diff 摘要
  let diffSummary = "";
  if (toolName === "file_edit" && call.content && typeof call.content === "object") {
    const c = call.content as Record<string, unknown>;
    const path = String(c.path ?? "").split("/").pop() || "";
    diffSummary = path ? `✏️ ${path}` : "";
  } else if ((toolName === "file_write" || toolName === "file_read") && call.content && typeof call.content === "object") {
    const c = call.content as Record<string, unknown>;
    const path = String(c.path ?? "").split("/").pop() || "";
    diffSummary = path ? `${icon} ${path}` : "";
  } else if (toolName === "shell_exec" && call.content && typeof call.content === "object") {
    const c = call.content as Record<string, unknown>;
    diffSummary = String(c.command ?? "").slice(0, 60);
  } else if (toolName === "code_search" && call.content && typeof call.content === "object") {
    const c = call.content as Record<string, unknown>;
    diffSummary = `/${String(c.pattern ?? "")}/`;
  }

  return (
    <div className={`overflow-hidden rounded-lg border ${
      isError ? "border-red-500/20 bg-red-500/[0.03]"
      : isRunning ? "border-blue-500/20 bg-blue-500/[0.02]"
      : "border-white/[0.06] bg-white/[0.015]"
    }`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left"
      >
        {open ? <ChevronDown size={12} className="text-neutral-600" /> : <ChevronRight size={12} className="text-neutral-600" />}
        <span className="text-sm">{icon}</span>
        <span className="text-xs font-medium text-neutral-300">{label}</span>
        <span className="flex-1 truncate text-[11px] text-neutral-600">
          {diffSummary || args.slice(0, 80)}
        </span>
        {isRunning ? (
          <Loader2 size={12} className="animate-spin text-blue-400" />
        ) : isError ? (
          <XCircle size={12} className="text-red-400" />
        ) : (
          <CheckCircle2 size={12} className="text-green-400/70" />
        )}
      </button>
      {open && (
        <div className="border-t border-white/[0.04] px-3 py-2">
          {/* file_edit diff 视图 */}
          {toolName === "file_edit" && call.content && typeof call.content === "object" && (() => {
            const c = call.content as Record<string, unknown>;
            const oldText = String(c.old_text ?? "");
            const newText = String(c.new_text ?? "");
            if (!oldText && !newText) return null;
            return (
              <div className="mb-2 overflow-hidden rounded bg-black/40 text-[11px] leading-5">
                {oldText && (
                  <div className="border-b border-white/[0.04] px-2 py-1">
                    {oldText.split("\n").slice(0, 8).map((line, li) => (
                      <div key={li} className="text-red-400/70"><span className="mr-2 select-none text-red-500/50">-</span>{line}</div>
                    ))}
                    {oldText.split("\n").length > 8 && <div className="text-neutral-600">  ... ({oldText.split("\n").length - 8} more)</div>}
                  </div>
                )}
                {newText && (
                  <div className="px-2 py-1">
                    {newText.split("\n").slice(0, 8).map((line, li) => (
                      <div key={li} className="text-green-400/70"><span className="mr-2 select-none text-green-500/50">+</span>{line}</div>
                    ))}
                    {newText.split("\n").length > 8 && <div className="text-neutral-600">  ... ({newText.split("\n").length - 8} more)</div>}
                  </div>
                )}
              </div>
            );
          })()}
          {/* 普通输入/输出 */}
          {toolName !== "file_edit" && args && (
            <div className="mb-2">
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-neutral-600">输入</div>
              <pre className="max-h-32 overflow-auto rounded bg-black/30 p-2 text-[11px] leading-5 text-neutral-400">
                {args.slice(0, 1000)}
              </pre>
            </div>
          )}
          {output && (
            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-neutral-600">输出</div>
              <pre className={`max-h-48 overflow-auto rounded bg-black/30 p-2 text-[11px] leading-5 ${
                isError ? "text-red-400/80" : "text-green-300/70"
              }`}>
                {output.slice(0, 2000)}
                {output.length > 2000 && "\n... (已截断)"}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  消息块                                                             */
/* ================================================================== */

/** 复制按钮组件 */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [text]);
  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.06] px-2.5 py-1.5 text-xs text-neutral-500 transition hover:border-white/[0.12] hover:text-neutral-300"
      title="复制回答"
    >
      {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
      {copied ? "已复制" : "复制"}
    </button>
  );
}

function MessageBlock({ msg }: { msg: ChatMessage }) {
  const timeStr = msg.timestamp
    ? new Date(msg.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
    : null;

  if (msg.role === "user") {
    return (
      <div className="flex justify-end py-2">
        <div className="flex items-start gap-3">
          <div className="max-w-[85%] rounded-2xl bg-white/[0.08] px-4 py-3 text-sm leading-7 text-neutral-100">
            <div className="whitespace-pre-wrap">{msg.content}</div>
            {timeStr && <div className="mt-1 text-right text-[10px] text-neutral-600">{timeStr}</div>}
          </div>
          <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/[0.08]">
            <UserRound size={14} className="text-neutral-400" />
          </div>
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="py-3">
      <div className="flex items-start gap-3">
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/[0.06] bg-white/[0.05]">
          <Bot size={14} className="text-neutral-400" />
        </div>
        <div className="min-w-0 flex-1">
          {/* 工具执行记录（折叠） */}
          {msg.steps && msg.steps.length > 0 && (
            <CollapsibleSection
              title="执行过程"
              icon={<Terminal size={12} />}
              badge={`${msg.steps.filter((s) => s.kind === "tool_call").length} 次工具调用`}
            >
              <ToolExecutionPanel steps={msg.steps} />
            </CollapsibleSection>
          )}

          {/* Markdown 渲染的最终回答 */}
          <div className="mt-1">
            <MarkdownRenderer content={msg.content} />
          </div>

          {/* 运行详情链接 + 复制按钮 */}
          <div className="mt-3 flex items-center gap-2">
            {msg.runId && (
              <Link
                to={`/runs/${encodeURIComponent(msg.runId)}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.06] px-2.5 py-1.5 text-xs text-neutral-500 transition hover:border-white/[0.12] hover:text-neutral-300"
              >
                <FileText size={12} />
                查看运行详情
              </Link>
            )}
            <CopyButton text={msg.content} />
            {timeStr && <span className="text-[10px] text-neutral-600">{timeStr}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
