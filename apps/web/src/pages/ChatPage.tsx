import { memo, useEffect, useRef, useState, useCallback } from "react";
import {
  ArrowDown, ArrowUp, Check, ChevronDown, ChevronRight, Copy, Loader2, RotateCw, Square, XCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { runAgent, type AgentRun } from "../api";
import { readAgentRunStream, type StepInfo, type TokenUsage } from "../api/chatStream";
import { getToken } from "../api/client";
import { getLLMConfig, updateLLMConfig } from "../api";
import { useShellActions, useShellStore } from "../shell/useShellStore";
import { MarkdownRenderer } from "../components/chat/MarkdownRenderer";
import { copyToClipboard } from "../lib/clipboard";
import { useEscapeClose } from "../hooks/useEscapeClose";
import CheckpointTimeline from "../components/checkpoints/CheckpointTimeline.tsx";
import {
  resolveInitialConversationId,
  shouldLoadConversationHistory, shouldResetChatSession, withStreamingConversationHistoryGuard,
} from "./chatSessionLifecycle";

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
  timestamp?: number;
}

/* ================================================================== */
/*  模型预设                                                           */
/* ================================================================== */

const MODEL_PRESETS = [
  { id: "deepseek-v4-flash", label: "DeepSeek V4 Flash" },
  { id: "deepseek-chat", label: "DeepSeek Chat" },
  { id: "deepseek-reasoner", label: "DeepSeek Reasoner" },
  { id: "gpt-4o-mini", label: "GPT-4o Mini" },
  { id: "gpt-4o", label: "GPT-4o" },
  { id: "claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
  { id: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
];

/* ================================================================== */
/*  主页面                                                             */
/* ================================================================== */

export default function ChatPage() {
  const { appendActivity, syncRunTask } = useShellActions();
  const chatSessionVersion = useShellStore((s) => s.chatSessionVersion);
  const chatSessionKey = useShellStore((s) => s.chatSessionKey);
  const activeConversationId = useShellStore((s) => s.activeConversationId);
  const setActiveConversationId = useShellStore((s) => s.setActiveConversationId);

  const [goal, setGoal] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(() =>
    resolveInitialConversationId(
      activeConversationId,
      localStorage.getItem("xagent_conversation_id"),
    ),
  );
  const [streamingText, setStreamingText] = useState("");
  const [completedSegments, setCompletedSegments] = useState<string[]>([]);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage | null>(null);
  const [model, setModel] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false); const [streamingConversationId, setStreamingConversationId] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const modelRef = useRef<HTMLDivElement>(null);
  // regenerate 的最新引用（供稳定回调使用，避免每次渲染创建新闭包）
  const regenerateRef = useRef<() => Promise<void>>(async () => {});
  const previousChatSessionKeyRef = useRef<string | null>(null);

  // 加载当前模型
  useEffect(() => {
    getLLMConfig().then((cfg) => setModel(cfg.default_model)).catch(() => {});
  }, []);

  // 点击外部关闭模型下拉
  useEffect(() => {
    if (!modelOpen) return;
    const handler = (e: MouseEvent) => {
      if (!modelRef.current?.contains(e.target as Node)) setModelOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelOpen]);

  // Esc 关闭模型选择下拉（键盘可达性）
  useEscapeClose(modelOpen, () => setModelOpen(false));

  useEffect(() => {
    if (conversationId) {
      localStorage.setItem("xagent_conversation_id", conversationId);
      setActiveConversationId(conversationId);
    } else {
      localStorage.removeItem("xagent_conversation_id");
    }
  }, [conversationId, setActiveConversationId]);

  useEffect(() => {
    const previousSessionKey = previousChatSessionKeyRef.current;
    previousChatSessionKeyRef.current = chatSessionKey;
    if (!shouldResetChatSession(previousSessionKey, chatSessionKey)) return;
    setGoal(""); setMessages([]); setLoading(false);
    setError(null); setConversationId(null); setSteps([]); setStreamingText("");
    setCompletedSegments([]); setLoadingHistory(false); setStreamingConversationId(null);
  }, [chatSessionVersion, chatSessionKey]);

  // 当侧栏选择对话时同步
  useEffect(() => {
    if (activeConversationId && activeConversationId !== conversationId) {
      setStreamingConversationId(null); setConversationId(activeConversationId);
      setSteps([]); setStreamingText(""); setError(null); setMessages([]);
    }
  }, [activeConversationId]);  // eslint-disable-line react-hooks/exhaustive-deps

  // 智能滚动
  const isNearBottomRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    isNearBottomRef.current = near;
    setAtBottom(near);
  }, []);

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (isNearBottomRef.current) {
      scrollRef.current?.scrollTo({
        top: scrollRef.current.scrollHeight,
        // 流式输出中平滑跟随；历史加载/会话切换（loading=false）瞬时定位，避免从顶部播放一段滚动动画
        behavior: loading ? "smooth" : "auto",
      });
    }
  }, [messages, loading, steps, streamingText]);

  // 恢复/切换会话时加载消息
  useEffect(() => {
    if (!shouldLoadConversationHistory(conversationId, streamingConversationId)) return;
    let cancelled = false;
    setLoadingHistory(true);
    const token = getToken();
    fetch(`/api/v1/stream/conversations/${conversationId}/messages`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled) return;
        if (data?.messages?.length) {
          setMessages(data.messages.map((m: { role: string; content: string }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
          })));
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoadingHistory(false); });
    return () => { cancelled = true; };
  }, [conversationId]);  // eslint-disable-line react-hooks/exhaustive-deps -- guard cleanup must not reload history

  // 快捷键
  useEffect(() => {
    textareaRef.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && loading) handleStop();
      if (e.key === "/" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); textareaRef.current?.focus(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [loading]);  // eslint-disable-line react-hooks/exhaustive-deps

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    textareaRef.current?.focus();
  }, []);

  const handleModelSwitch = async (modelId: string) => {
    setModel(modelId);
    setModelOpen(false);
    textareaRef.current?.focus();
    try { await updateLLMConfig({ default_model: modelId }); } catch { /* silent */ }
  };

  const submit = useCallback(async (overrideText?: string) => {
    const nextGoal = (overrideText ?? goal).trim();
    if (!nextGoal || loading) return;
    setGoal(""); setError(null); setSteps([]); setStreamingText(""); setCompletedSegments([]); setTokenUsage(null);
    // 重置 textarea 高度
    if (textareaRef.current) textareaRef.current.style.height = "auto";
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
      setLoading(false); setStreamingText(""); setCompletedSegments([]);
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

    await withStreamingConversationHistoryGuard(
      setStreamingConversationId,
      (onStarted) => readAgentRunStream(resp, {
        onStarted: (convId) => {
          onStarted(convId); setConversationId(convId);
        },
        onToken: (t) => { tokenBuf += t; setStreamingText(tokenBuf); },
        onFinalAnswer: (text) => { result = text; if (!tokenBuf) setStreamingText(text); },
        onError: setError,
        onStep: (step) => {
          collectedSteps.push(step);
          setSteps([...collectedSteps]);
          if (step.kind === "tool_call") {
            if (tokenBuf.trim()) { segments.push(tokenBuf.trim()); setCompletedSegments([...segments]); }
            tokenBuf = ""; setStreamingText("");
          }
        },
        onDone: (nextRunId, usage) => {
          sseRunId = nextRunId;
          if (usage) setTokenUsage(usage);
          syncRunTask(nextRunId, { source: "chat" });
          appendActivity({ taskId: "chat", title: "任务完成", detail: `运行 ${nextRunId}`, tone: "success" });
        },
        onProgress: () => {},
      }),
    );

    let finalContent = result || [...segments, tokenBuf].filter(Boolean).join("\n\n");
    if (!finalContent && collectedSteps.length > 0) {
      const toolCallCount = collectedSteps.filter((s) => s.kind === "tool_call").length;
      finalContent = `任务已执行完成（共 ${toolCallCount} 次工具调用），但模型未生成文字总结。`;
    }
    if (sseRunId || finalContent) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: finalContent, runId: sseRunId, steps: [...collectedSteps], timestamp: Date.now() },
      ]);
    }
  }

  /* 重新生成：截断到最后一条用户消息并重跑 */
  async function regenerate() {
    if (loading) return;
    const lastUserIdx = messages.map((m) => m.role).lastIndexOf("user");
    if (lastUserIdx < 0) return;
    const lastUserContent = messages[lastUserIdx].content;
    setMessages(messages.slice(0, lastUserIdx + 1));
    setError(null); setSteps([]); setStreamingText(""); setCompletedSegments([]); setTokenUsage(null);
    setLoading(true);
    try {
      await runSSE(lastUserContent);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setMessages((prev) => [...prev, { role: "assistant", content: "（已停止）" }]);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoading(false); setStreamingText(""); setCompletedSegments([]);
      abortRef.current = null;
    }
  }
  regenerateRef.current = regenerate;

  // 稳定引用：流式输出期间不导致 MessageBlock 重渲染
  const handleRegenerate = useCallback(() => { void regenerateRef.current(); }, []);

  const isEmpty = messages.length === 0 && !loading && !error && !loadingHistory;
  const modelLabel = MODEL_PRESETS.find((m) => m.id === model)?.label || model || "选择模型";

  /* ── 输入框组件（复用） ── */
  const InputBox = (
    <div className="w-full">
      <div className="relative flex items-end gap-2 rounded-2xl border border-white/[0.1] bg-[#1a1a1a] px-4 py-3 shadow-[0_2px_12px_rgba(0,0,0,0.3)] transition-colors focus-within:border-white/[0.18]">
        {/* 模型选择器 pill */}
        <div className="relative" ref={modelRef}>
          <button
            type="button"
            onClick={() => setModelOpen(!modelOpen)}
            className="mb-0.5 flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[11px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
          >
            <span className="max-w-[90px] truncate">{modelLabel}</span>
            <ChevronDown size={10} />
          </button>
          {modelOpen && (
            <div className="absolute bottom-full left-0 z-50 mb-2 w-52 rounded-lg border border-white/[0.08] bg-[#1e1e1e] py-1.5 shadow-xl shadow-black/30">
              {MODEL_PRESETS.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => handleModelSwitch(m.id)}
                  className={`flex w-full items-center px-3.5 py-2 text-left text-[12px] transition hover:bg-white/[0.05] ${
                    model === m.id ? "font-medium text-white" : "text-neutral-400"
                  }`}
                >
                  {m.label}
                  {model === m.id && <Check size={12} className="ml-auto text-green-500" />}
                </button>
              ))}
            </div>
          )}
        </div>

        <textarea
          ref={textareaRef}
          className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-[14px] leading-6 text-neutral-100 outline-none placeholder:text-neutral-600"
          placeholder="描述一个任务..."
          rows={1}
          value={goal}
          onChange={(e) => {
            setGoal(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
          }}
          onKeyDown={(e) => {
            // isComposing：中文/日文 IME 候选词确认期间不发送，防止回车误提交
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); }
          }}
        />
        {loading ? (
          <button
            type="button"
            onClick={handleStop}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-neutral-700 text-neutral-200 transition hover:bg-neutral-600"
            title="停止 (Esc)"
            aria-label="停止生成"
          >
            <Square size={12} fill="currentColor" />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!goal.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-black transition hover:bg-neutral-200 disabled:opacity-20"
            title="发送 (Enter)"
            aria-label="发送"
          >
            <ArrowUp size={15} strokeWidth={2.5} />
          </button>
        )}
      </div>
    </div>
  );

  /* ── 加载历史消息过渡 ── */
  if (loadingHistory) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="xb-thinking-dots"><span /><span /><span /></span>
      </div>
    );
  }

  /* ── 空态：居中 hero + 输入框 ── */
  if (isEmpty) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center overflow-hidden px-6">
        {/* 微妙环境光（静态径向渐变，非动画） */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(620px 300px at 50% 38%, rgba(255,255,255,0.02), transparent 70%)",
          }}
        />
        <div className="relative w-full max-w-[680px]">
          <h1 className="mb-8 text-center text-[22px] font-medium tracking-tight text-neutral-100">
            有什么可以帮你的？
          </h1>
          {InputBox}
          {/* 建议 chips */}
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void submit(s)}
                className="rounded-full border border-white/[0.07] bg-white/[0.03] px-3.5 py-1.5 text-[12px] text-neutral-500 transition-all duration-150 hover:-translate-y-px hover:border-white/[0.16] hover:bg-white/[0.06] hover:text-neutral-200"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  /* ── 对话态 ── */
  return (
    <div className="flex h-full flex-col">
      {/* 消息流 */}
      <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onScroll={handleScroll} className="xagent-scrollbar h-full overflow-y-auto">
        <div className="mx-auto max-w-[720px] px-5 py-8">
          {(() => {
            const lastAssistantIdx = messages.map((m) => m.role).lastIndexOf("assistant");
            return messages.map((msg, i) => (
              <MessageBlock
                key={i}
                msg={msg}
                canRegenerate={i === lastAssistantIdx && !loading}
                onRegenerate={handleRegenerate}
              />
            ));
          })()}

          {/* 实时流式区 */}
          {loading && (
            <div className="xb-fade-up py-4">
              {steps.length > 0 && <InlineToolSteps steps={steps} live />}

              {/* 状态行 */}
              <div className="mt-3 flex items-center gap-2.5 text-[13px] text-neutral-500">
                {steps.length === 0 && !streamingText && !completedSegments.length ? (
                  <>
                    <span className="xb-thinking-dots"><span /><span /><span /></span>
                    <span className="text-neutral-600">正在思考</span>
                  </>
                ) : (
                  <>
                    <Loader2 size={13} className="animate-spin text-neutral-600" />
                    <CurrentActionText steps={steps} />
                    <span className="text-neutral-700">·</span>
                    <ElapsedTimer />
                  </>
                )}
              </div>

              {/* 流式文本 + 光标 */}
              {(() => {
                const displayText = [...completedSegments, streamingText].filter(Boolean).join("\n\n");
                return displayText ? (
                  <div className="mt-3">
                    <MarkdownRenderer content={displayText} />
                    <span className="xb-cursor" />
                  </div>
                ) : null;
              })()}
            </div>
          )}

          {/* 错误 */}
          {error && (
            <div className="mt-4 flex items-center gap-2 text-sm text-red-400">
              <XCircle size={14} className="shrink-0" />
              <span>{error}</span>
              <button
                onClick={() => void regenerate()}
                className="ml-2 flex items-center gap-1 text-xs text-red-300/70 underline underline-offset-2 transition hover:text-red-200"
              >
                <RotateCw size={11} />
                重试
              </button>
            </div>
          )}
          {conversationId && (
            <div className="mt-6">
              <CheckpointTimeline conversationId={conversationId} compact />
            </div>
          )}
        </div>
      </div>

      {/* 回到底部 */}
      {!atBottom && (
        <button
          type="button"
          title="回到底部"
          aria-label="回到底部"
          onClick={scrollToBottom}
          className="xb-fade-up absolute bottom-3 left-1/2 z-10 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-white/[0.1] bg-[#1a1a1a] text-neutral-400 shadow-lg shadow-black/30 transition hover:border-white/[0.2] hover:text-neutral-200"
        >
          <ArrowDown size={14} />
        </button>
      )}
      </div>

      {/* 底部输入区 */}
      <div className="shrink-0 px-5 pb-5 pt-2">
        <div className="mx-auto max-w-[720px]">
          {InputBox}
          {tokenUsage && (
            <div className="mt-2 text-center text-[11px] tabular-nums text-neutral-700">
              {(tokenUsage.promptTokens + tokenUsage.completionTokens).toLocaleString()} tokens
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  计时器 + 当前动作                                                  */
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
  return <span className="tabular-nums text-neutral-600">{mm > 0 ? `${mm}m${ss}s` : `${ss}s`}</span>;
}

function CurrentActionText({ steps }: { steps: StepInfo[] }) {
  const lastCall = [...steps].reverse().find((s) => s.kind === "tool_call");
  const lastResult = [...steps].reverse().find((s) => s.kind === "tool_result");
  const isExecuting = lastCall && (!lastResult || steps.indexOf(lastResult) < steps.indexOf(lastCall));
  if (isExecuting && lastCall?.tool) {
    return <span className="text-neutral-400">{TOOL_LABELS[lastCall.tool] || lastCall.tool}</span>;
  }
  if (steps.length > 0) return <span className="text-neutral-500">整合结果</span>;
  return <span className="text-neutral-500">思考中</span>;
}

/* ================================================================== */
/*  建议                                                               */
/* ================================================================== */

const SUGGESTIONS = [
  "写一个 Python 脚本计算斐波那契数列",
  "创建一个 FastAPI 项目骨架",
  "分析当前项目的依赖关系",
  "运行测试并修复失败用例",
];

/* ================================================================== */
/*  工具调用 — Codex 内联行                                            */
/* ================================================================== */

const TOOL_LABELS: Record<string, string> = {
  python_exec: "执行 Python",
  shell_exec: "执行命令",
  web_fetch: "抓取网页",
  file_write: "写入文件",
  file_read: "读取文件",
  file_list: "列出目录",
  file_edit: "编辑文件",
  git: "Git 操作",
  code_search: "搜索代码",
  memory_write: "写入记忆",
  memory_search: "检索记忆",
  skill_exec: "执行技能",
};

/** 内联工具步骤列表 — 无卡片，纯行 */
function InlineToolSteps({ steps, live = false }: { steps: StepInfo[]; live?: boolean }) {
  const groups: { call: StepInfo; result?: StepInfo }[] = [];
  for (let i = 0; i < steps.length; i++) {
    if (steps[i].kind === "tool_call") {
      const result = steps[i + 1]?.kind === "tool_result" ? steps[i + 1] : undefined;
      groups.push({ call: steps[i], result });
      if (result) i++;
    }
  }

  return (
    <div className="space-y-px">
      {groups.map((g, i) => (
        <ToolLine key={i} call={g.call} result={g.result} />
      ))}
      {live && groups.length === 0 && (
        <div className="flex items-center gap-2 py-1 text-[13px] text-neutral-600">
          <Loader2 size={12} className="animate-spin" />
          <span>准备工具调用...</span>
        </div>
      )}
    </div>
  );
}

/** 单行工具调用 — Codex 风格 */
function ToolLine({ call, result }: { call: StepInfo; result?: StepInfo }) {
  const [open, setOpen] = useState(false);
  const toolName = call.tool || "tool";
  const label = TOOL_LABELS[toolName] || toolName;
  const isRunning = !result;
  const output = result?.content != null
    ? (typeof result.content === "string" ? result.content : JSON.stringify(result.content, null, 2))
    : "";
  const isError = output.startsWith("[错误]") || output.includes("失败");

  let summary = "";
  if (call.content && typeof call.content === "object") {
    const c = call.content as Record<string, unknown>;
    if (toolName === "shell_exec") summary = String(c.command ?? "").slice(0, 60);
    else if (toolName === "file_read" || toolName === "file_write" || toolName === "file_edit")
      summary = String(c.path ?? "").split("/").pop() || "";
    else if (toolName === "code_search") summary = `/${String(c.pattern ?? "")}/`;
    else if (toolName === "web_fetch") summary = String(c.url ?? "").slice(0, 50);
  }

  return (
    <div className="group/tool">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-white/[0.03]"
      >
        {open
          ? <ChevronDown size={12} className="shrink-0 text-neutral-700" />
          : <ChevronRight size={12} className="shrink-0 text-neutral-700" />
        }
        <span className="shrink-0 text-[13px] font-medium text-neutral-400">{label}</span>
        {summary && <span className="min-w-0 flex-1 truncate text-[12px] text-neutral-600">{summary}</span>}
        {!summary && <span className="flex-1" />}
        {isRunning ? (
          <Loader2 size={11} className="shrink-0 animate-spin text-neutral-500" />
        ) : isError ? (
          <XCircle size={11} className="shrink-0 text-red-400/70" />
        ) : (
          <Check size={11} className="shrink-0 text-green-500/60" />
        )}
      </button>
      {open && (
        <div className="ml-6 mb-1.5 mt-0.5">
          {call.content != null && (
            <pre className="max-h-28 overflow-auto rounded-lg bg-black/30 px-3 py-2 text-[11px] leading-5 text-neutral-500">
              {typeof call.content === "string" ? call.content.slice(0, 800) : JSON.stringify(call.content, null, 2).slice(0, 800)}
            </pre>
          )}
          {output && (
            <pre className={`mt-1 max-h-36 overflow-auto rounded-lg bg-black/30 px-3 py-2 text-[11px] leading-5 ${isError ? "text-red-400/70" : "text-neutral-500"}`}>
              {output.slice(0, 1500)}
              {output.length > 1500 && "\n..."}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  消息块 — Codex 风格：无气泡、纯文本                                 */
/* ================================================================== */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await copyToClipboard(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={() => void handleCopy()}
      className="text-neutral-700 transition hover:text-neutral-400"
      title="复制"
      aria-label="复制"
    >
      {copied ? <Check size={13} className="text-green-500" /> : <Copy size={13} />}
    </button>
  );
}

const MessageBlock = memo(function MessageBlock({ msg, canRegenerate, onRegenerate }: { msg: ChatMessage; canRegenerate?: boolean; onRegenerate?: () => void }) {
  if (msg.role === "user") {
    return (
      <div className="group/msg mb-8">
        <div className="mb-1 text-[13px] font-semibold text-neutral-200">你</div>
        <div className="whitespace-pre-wrap text-[14px] leading-7 text-neutral-300">{msg.content}</div>
        <div className="mt-1.5 flex items-center gap-3 opacity-0 transition-opacity group-hover/msg:opacity-100">
          <CopyButton text={msg.content} />
        </div>
      </div>
    );
  }

  // Assistant — 全宽无边界
  return (
    <div className="group/msg mb-8 xb-fade-up">
      <div className="mb-1 text-[13px] font-semibold text-neutral-500">熊宝</div>

      {/* 工具执行记录（内联折叠） */}
      {msg.steps && msg.steps.length > 0 && (
        <CompletedToolSection steps={msg.steps} />
      )}

      {/* 正文 */}
      <div className="text-[14px] leading-7 text-neutral-300">
        <MarkdownRenderer content={msg.content} />
      </div>

      {/* 底部操作行 */}
      <div className="mt-2 flex items-center gap-3 opacity-0 transition-opacity group-hover/msg:opacity-100">
        <CopyButton text={msg.content} />
        {canRegenerate && onRegenerate && (
          <button
            onClick={onRegenerate}
            className="flex items-center gap-1 text-[11px] text-neutral-700 transition hover:text-neutral-400"
            title="重新生成"
          >
            <RotateCw size={12} />
            重新生成
          </button>
        )}
        {msg.runId && (
          <Link
            to={`/runs/${encodeURIComponent(msg.runId)}`}
            className="text-[11px] text-neutral-700 transition hover:text-neutral-400"
          >
            运行详情
          </Link>
        )}
      </div>
    </div>
  );
});

/** 已完成消息中的工具区 — 默认折叠 */
const CompletedToolSection = memo(function CompletedToolSection({ steps }: { steps: StepInfo[] }) {
  const [open, setOpen] = useState(false);
  const toolCount = steps.filter((s) => s.kind === "tool_call").length;
  if (toolCount === 0) return null;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[12px] text-neutral-600 transition hover:text-neutral-400"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span>{toolCount} 次工具调用</span>
      </button>
      {open && (
        <div className="mt-1.5 border-l border-white/[0.06] pl-3">
          <InlineToolSteps steps={steps} />
        </div>
      )}
    </div>
  );
});
