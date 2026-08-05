import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUp, Bot, Sparkles, UserRound } from "lucide-react";

type MessageRole = "user" | "assistant";

interface CommandMessage {
  id: string;
  role: MessageRole;
  content: string;
}

export interface CommandReply {
  content: string;
  detail?: ReactNode;
}

export interface ConversationalCommandProps {
  title: string;
  context: string;
  placeholder: string;
  suggestions?: string[];
  compact?: boolean;
  className?: string;
  initialAssistantMessage?: string;
  onSubmit?: (value: string) => CommandReply | string | void | Promise<CommandReply | string | void>;
}

function makeId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function defaultAssistantReply(context: string, value: string) {
  return `已接收「${value}」。我会在「${context}」中把它转换成下一步可执行动作。`;
}

function resolveReply(reply: CommandReply | string | void, context: string, value: string): CommandReply {
  if (typeof reply === "string") return { content: reply };
  if (reply?.content) return reply;
  return { content: defaultAssistantReply(context, value) };
}

export default function ConversationalCommand({
  title,
  context,
  placeholder,
  suggestions = [],
  compact = false,
  className = "",
  initialAssistantMessage,
  onSubmit,
}: ConversationalCommandProps) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [messages, setMessages] = useState<CommandMessage[]>(
    initialAssistantMessage
      ? [{ id: "assistant-initial", role: "assistant", content: initialAssistantMessage }]
      : [],
  );
  const listRef = useRef<HTMLDivElement>(null);

  // 新消息/提交中自动滚动到底部
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, submitting]);

  async function submit(nextValue = value) {
    const clean = nextValue.trim();
    if (!clean || submitting) return;
    setSubmitting(true);
    setValue("");
    setMessages((current) => [...current, { id: makeId("user"), role: "user", content: clean }]);
    try {
      const rawReply = onSubmit ? await onSubmit(clean) : undefined;
      const reply = resolveReply(rawReply, context, clean);
      setMessages((current) => [
        ...current,
        { id: makeId("assistant"), role: "assistant", content: reply.content },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: makeId("assistant-error"),
          role: "assistant",
          content: error instanceof Error ? error.message : "指令处理失败，请重新描述目标。",
        },
      ]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className={`rounded-lg border border-white/[0.06] bg-white/[0.02] ${className}`}>
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[13px] font-medium text-neutral-200">
            <Sparkles size={14} className="text-neutral-500" />
            <span className="truncate">{title}</span>
          </div>
          <div className="mt-0.5 truncate text-[11px] text-neutral-600">{context}</div>
        </div>
        <span className="rounded-md border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[10px] font-medium text-neutral-500">
          对话驱动
        </span>
      </div>

      {(messages.length > 0 || submitting) && (
        <div ref={listRef} className={`xagent-scrollbar space-y-3 overflow-auto px-4 py-3 ${compact ? "max-h-44" : "max-h-64"}`}>
          {messages.map((message) => (
            <div key={message.id} className={`flex gap-2 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              {message.role === "assistant" && (
                <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white/[0.06] text-neutral-400">
                  <Bot size={13} />
                </span>
              )}
              <div
                className={`max-w-[82%] rounded-lg px-3 py-2 text-[13px] leading-6 ${
                  message.role === "user"
                    ? "border border-white/[0.08] bg-white/[0.05] text-neutral-200"
                    : "border border-white/[0.05] bg-transparent text-neutral-400"
                }`}
              >
                {message.content}
              </div>
              {message.role === "user" && (
                <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-white/[0.07] bg-white/[0.04] text-neutral-400">
                  <UserRound size={13} />
                </span>
              )}
            </div>
          ))}
          {submitting && (
            <div className="flex gap-2">
              <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white/[0.06] text-neutral-400">
                <Bot size={13} />
              </span>
              <div className="flex items-center rounded-lg border border-white/[0.05] px-3 py-2.5">
                <span className="xb-thinking-dots"><span /><span /><span /></span>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="px-4 pb-4 pt-3">
        {suggestions.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => void submit(suggestion)}
                className="rounded-md border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] text-neutral-400 transition hover:border-white/[0.16] hover:text-neutral-200"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        <div className="rounded-lg border border-white/[0.08] bg-[#141414] transition-colors focus-within:border-white/[0.16]">
          <textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder={placeholder}
            className={`block w-full resize-none border-0 bg-transparent px-4 py-3 text-[13px] leading-6 text-neutral-100 outline-none placeholder:text-neutral-600 ${compact ? "min-h-20" : "min-h-24"}`}
          />
          <div className="flex items-center justify-between border-t border-white/[0.06] px-3 py-2">
            <span className="text-[11px] text-neutral-600">Ctrl Enter 发送</span>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={submitting || !value.trim()}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-neutral-100 text-black transition hover:bg-white disabled:opacity-30"
              title="发送指令"
            >
              <ArrowUp size={15} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
