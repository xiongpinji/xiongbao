import { useState, type ReactNode } from "react";
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
    <section className={`xagent-command-shell xagent-sheen ${className}`}>
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.07] px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Sparkles size={15} className="text-[#d6ad62]" />
            <span className="truncate">{title}</span>
          </div>
          <div className="mt-1 truncate text-xs text-neutral-600">{context}</div>
        </div>
        <span className="rounded-full border border-[#8a6a32]/35 bg-[#171208] px-2.5 py-1 text-xs font-medium text-[#f2d99c] shadow-[inset_0_1px_0_rgba(255,232,180,0.12)]">
          对话驱动
        </span>
      </div>

      {messages.length > 0 && (
        <div className={`xagent-scrollbar space-y-3 overflow-auto px-4 py-3 ${compact ? "max-h-44" : "max-h-64"}`}>
          {messages.map((message) => (
            <div key={message.id} className={`flex gap-2 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              {message.role === "assistant" && (
                <span className="xagent-icon-tile mt-1 h-7 w-7 rounded-xl">
                  <Bot size={14} />
                </span>
              )}
              <div
                className={`max-w-[82%] rounded-2xl px-3 py-2 text-sm leading-6 ${
                  message.role === "user"
                    ? "xagent-message-user border"
                    : "xagent-message-assistant border"
                }`}
              >
                {message.content}
              </div>
              {message.role === "user" && (
                <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border border-white/[0.07] bg-white/[0.045] text-neutral-400">
                  <UserRound size={14} />
                </span>
              )}
            </div>
          ))}
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
                className="xagent-chip text-xs"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        <div className="xagent-composer-frame">
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
            className={`block w-full resize-none border-0 bg-transparent px-4 py-3 text-sm leading-6 text-neutral-100 outline-none placeholder:text-neutral-600 ${compact ? "min-h-20" : "min-h-24"}`}
          />
          <div className="flex items-center justify-between border-t border-white/[0.07] px-3 py-2">
            <span className="text-xs text-neutral-600">Ctrl Enter 发送</span>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={submitting || !value.trim()}
              className="xagent-send-button h-9 w-9"
              title="发送指令"
            >
              <ArrowUp size={17} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
