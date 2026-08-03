import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bot,
  CreditCard,
  Grid2X2,
  MessageSquarePlus,
  MessageSquareText,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Target,
  Database,
} from "lucide-react";
import { useShellActions, useShellStore } from "../../shell/useShellStore";
import { useHotkeys } from "../../hooks/useHotkeys";

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: typeof Search;
  keywords: string;
  run: (navigate: (to: string) => void, actions: ReturnType<typeof useShellActions>) => void;
}

const COMMANDS: Command[] = [
  {
    id: "new-chat",
    label: "新建对话",
    hint: "⌘N",
    icon: MessageSquarePlus,
    keywords: "new chat 对话 新建",
    run: (navigate, actions) => { actions.resetChatSession(); navigate("/chat"); },
  },
  {
    id: "chat",
    label: "返回对话",
    icon: MessageSquareText,
    keywords: "chat 对话 聊天 首页",
    run: (navigate) => navigate("/chat"),
  },
  {
    id: "goal-board",
    label: "目标看板",
    icon: Target,
    keywords: "goal board 目标 看板 任务",
    run: (navigate) => navigate("/goal-board"),
  },
  {
    id: "workflow",
    label: "工作流",
    icon: Grid2X2,
    keywords: "workflow 工作流 流程",
    run: (navigate) => navigate("/professional?mode=workflow"),
  },
  {
    id: "agents",
    label: "智能体",
    icon: Bot,
    keywords: "agents 智能体 机器人",
    run: (navigate) => navigate("/agents"),
  },
  {
    id: "settings",
    label: "设置",
    icon: Settings,
    keywords: "settings 设置 配置",
    run: (navigate) => navigate("/settings"),
  },
  {
    id: "models",
    label: "模型配置",
    icon: Server,
    keywords: "models 模型 llm 配置",
    run: (navigate) => navigate("/settings?section=models"),
  },
  {
    id: "memory",
    label: "记忆库",
    icon: Database,
    keywords: "memory 记忆 知识库",
    run: (navigate) => navigate("/memory"),
  },
  {
    id: "billing",
    label: "计费用量",
    icon: CreditCard,
    keywords: "billing 计费 用量 账单",
    run: (navigate) => navigate("/billing"),
  },
  {
    id: "audit",
    label: "审计日志",
    icon: ShieldCheck,
    keywords: "audit 审计 日志 安全",
    run: (navigate) => navigate("/audit"),
  },
];

export default function CommandPalette() {
  const open = useShellStore((state) => state.commandPaletteOpen);
  const { setCommandPaletteOpen } = useShellActions();
  const navigate = useNavigate();
  const actions = useShellActions();

  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // 记录打开命令面板前聚焦的元素，关闭时归还焦点
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // ⌘K / Ctrl+K 全局切换命令面板（侧栏已宣传该快捷键，必须真实生效）
  useHotkeys(
    ["ctrl+k", "meta+k"],
    () => setCommandPaletteOpen(!open),
    { enableInInputs: true },
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return COMMANDS;
    return COMMANDS.filter(
      (c) => c.label.toLowerCase().includes(q) || c.keywords.toLowerCase().includes(q),
    );
  }, [query]);

  // 打开时重置 + 聚焦；关闭时归还焦点给打开前聚焦的元素（避免键盘用户焦点丢失）
  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    setQuery("");
    setActiveIndex(0);
    setTimeout(() => inputRef.current?.focus(), 10);
    return () => {
      restoreFocusRef.current?.focus?.();
    };
  }, [open]);

  // 过滤变化时重置选中
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  // Esc 关闭（全局）
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCommandPaletteOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, setCommandPaletteOpen]);

  // 滚动选中项到可视区
  useEffect(() => {
    const el = listRef.current?.children[activeIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (!open) return null;

  const execute = (cmd: Command) => {
    setCommandPaletteOpen(false);
    cmd.run(navigate, actions);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % Math.max(filtered.length, 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + filtered.length) % Math.max(filtered.length, 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const cmd = filtered[activeIndex];
      if (cmd) execute(cmd);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[14vh] backdrop-blur-[2px]"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setCommandPaletteOpen(false); }}
    >
      <div className="xb-fade-up w-full max-w-lg overflow-hidden rounded-lg border border-white/[0.08] bg-[#161616] shadow-[0_16px_56px_rgba(0,0,0,0.5)]">
        {/* 搜索输入 */}
        <div className="flex items-center gap-2.5 border-b border-white/[0.06] px-4 py-3">
          <Search size={15} className="shrink-0 text-neutral-600" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="搜索命令或页面..."
            className="flex-1 bg-transparent text-[13px] text-neutral-100 outline-none placeholder:text-neutral-600"
            spellCheck={false}
          />
          <kbd className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-neutral-600">Esc</kbd>
        </div>

        {/* 结果列表 */}
        <div ref={listRef} className="xagent-scrollbar max-h-[320px] overflow-y-auto p-1.5">
          {filtered.length === 0 && (
            <div className="px-3 py-8 text-center text-[12px] text-neutral-600">
              没有匹配的命令
            </div>
          )}
          {filtered.map((cmd, i) => {
            const Icon = cmd.icon;
            const active = i === activeIndex;
            return (
              <button
                key={cmd.id}
                type="button"
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => execute(cmd)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left transition ${
                  active ? "bg-white/[0.07] text-neutral-100" : "text-neutral-400"
                }`}
              >
                <Icon size={15} className={active ? "text-neutral-200" : "text-neutral-600"} />
                <span className="flex-1 text-[13px]">{cmd.label}</span>
                {cmd.hint && (
                  <kbd className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[10px] text-neutral-600">
                    {cmd.hint}
                  </kbd>
                )}
                {active && !cmd.hint && (
                  <kbd className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[10px] text-neutral-600">↵</kbd>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
