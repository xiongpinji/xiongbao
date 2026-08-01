import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Plus, Trash2, Loader2 } from "lucide-react";
import { getToken } from "../../api/client";

export interface ConversationItem {
  conversation_id: string;
  title: string;
  message_count: number;
  created_at: number;
  last_active: number;
}

interface Props {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

export default function ConversationSidebar({ activeId, onSelect, onNew }: Props) {
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchList = useCallback(async () => {
    try {
      const token = getToken();
      const resp = await fetch("/api/v1/stream/conversations", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) return;
      const data = await resp.json();
      setItems(data.conversations || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList();
    // 每 15 秒刷新
    const timer = setInterval(() => void fetchList(), 15000);
    return () => clearInterval(timer);
  }, [fetchList]);

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    const token = getToken();
    await fetch(`/api/v1/stream/conversations/${id}`, {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    setItems((prev) => prev.filter((c) => c.conversation_id !== id));
    if (activeId === id) onNew();
  }

  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r border-white/[0.06] bg-[#0d0d0d]">
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-3">
        <span className="text-xs font-medium text-neutral-500">对话历史</span>
        <button
          type="button"
          onClick={onNew}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.08] text-neutral-500 transition hover:border-white/[0.15] hover:text-neutral-200"
          title="新对话"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* 列表 */}
      <div className="xagent-scrollbar min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={16} className="animate-spin text-neutral-600" />
          </div>
        ) : items.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-neutral-700">
            暂无对话记录
          </div>
        ) : (
          <div className="space-y-0.5">
            {items.map((item) => (
              <button
                key={item.conversation_id}
                type="button"
                onClick={() => onSelect(item.conversation_id)}
                className={`group flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition ${
                  activeId === item.conversation_id
                    ? "bg-white/[0.07] text-neutral-200"
                    : "text-neutral-500 hover:bg-white/[0.03] hover:text-neutral-300"
                }`}
              >
                <MessageSquare size={14} className="mt-0.5 shrink-0 opacity-50" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium leading-5">
                    {item.title}
                  </div>
                  <div className="mt-0.5 text-[10px] text-neutral-700">
                    {item.message_count} 条消息 · {timeAgo(item.last_active)}
                  </div>
                </div>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => void handleDelete(e, item.conversation_id)}
                  onKeyDown={(e) => { if (e.key === "Enter") void handleDelete(e as unknown as React.MouseEvent, item.conversation_id); }}
                  className="mt-0.5 hidden shrink-0 rounded p-0.5 text-neutral-700 transition hover:text-red-400 group-hover:block"
                >
                  <Trash2 size={12} />
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
