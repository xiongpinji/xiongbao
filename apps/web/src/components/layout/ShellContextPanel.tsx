import { useState, useRef, useCallback } from "react";
import {
  Activity,
  CheckCircle2,
  ChevronRight,
  Clock3,
  ExternalLink,
  Globe,
  KanbanSquare,
  Loader2,
  PanelRightClose,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useShellDerivedState } from "../../shell/useShellStore";
import { formatTime } from "../../lib/time";

/* ── Tab 定义 ── */
type TabId = "preview" | "tasks" | "activity";

const TABS: { id: TabId; label: string; icon: typeof Globe }[] = [
  { id: "preview", label: "预览", icon: Globe },
  { id: "tasks", label: "任务", icon: KanbanSquare },
  { id: "activity", label: "动态", icon: Activity },
];

/* ================================================================== */
/*  主面板                                                             */
/* ================================================================== */

export default function ShellContextPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<TabId>("preview");

  return (
    <aside className="xb-panel-right flex h-full w-[380px] shrink-0 flex-col border-l border-white/[0.05] bg-[#0f0f0f]">
      {/* 顶部 Tab 栏 */}
      <div className="flex h-11 shrink-0 items-center border-b border-white/[0.05] px-2">
        <div className="flex flex-1 items-center gap-0.5">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12px] transition ${
                tab === id
                  ? "bg-white/[0.08] font-medium text-neutral-100"
                  : "text-neutral-500 hover:bg-white/[0.04] hover:text-neutral-300"
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          title="关闭面板"
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-600 transition hover:bg-white/[0.06] hover:text-neutral-300"
        >
          <PanelRightClose size={14} />
        </button>
      </div>

      {/* 内容区 */}
      <div className="min-h-0 flex-1">
        {tab === "preview" && <PreviewTab />}
        {tab === "tasks" && <TasksTab />}
        {tab === "activity" && <ActivityTab />}
      </div>
    </aside>
  );
}

/* ================================================================== */
/*  预览 Tab — 内置浏览器                                              */
/* ================================================================== */

function PreviewTab() {
  const [url, setUrl] = useState("http://localhost:5175");
  const [inputUrl, setInputUrl] = useState("http://localhost:5175");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const navigate = useCallback(() => {
    let target = inputUrl.trim();
    if (!target) return;
    if (!/^https?:\/\//.test(target)) target = `http://${target}`;
    setUrl(target);
    setLoading(true);
    setError(false);
  }, [inputUrl]);

  const refresh = useCallback(() => {
    if (iframeRef.current) {
      setLoading(true);
      setError(false);
      iframeRef.current.src = url;
    }
  }, [url]);

  return (
    <div className="flex h-full flex-col">
      {/* URL 栏 */}
      <div className="flex shrink-0 items-center gap-1.5 border-b border-white/[0.04] px-2.5 py-2">
        <div className="flex flex-1 items-center gap-2 rounded-lg bg-white/[0.04] px-2.5 py-1.5">
          <Globe size={12} className="shrink-0 text-neutral-600" />
          <input
            type="text"
            value={inputUrl}
            onChange={(e) => setInputUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") navigate(); }}
            className="flex-1 bg-transparent text-[12px] text-neutral-300 outline-none placeholder:text-neutral-700"
            placeholder="输入 URL..."
            spellCheck={false}
          />
        </div>
        <button
          type="button"
          title="刷新"
          onClick={refresh}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-neutral-600 transition hover:bg-white/[0.06] hover:text-neutral-300"
        >
          <RefreshCw size={12} />
        </button>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          title="在浏览器中打开"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-neutral-600 transition hover:bg-white/[0.06] hover:text-neutral-300"
        >
          <ExternalLink size={12} />
        </a>
      </div>

      {/* iframe */}
      <div className="relative min-h-0 flex-1 bg-white">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0f0f0f]">
            <Loader2 size={18} className="animate-spin text-neutral-600" />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-[#0f0f0f]">
            <XCircle size={20} className="text-neutral-700" />
            <span className="text-[12px] text-neutral-600">无法加载页面</span>
            <button
              type="button"
              onClick={refresh}
              className="mt-1 rounded-md bg-white/[0.06] px-3 py-1.5 text-[11px] text-neutral-400 transition hover:bg-white/[0.1]"
            >
              重试
            </button>
          </div>
        )}
        <iframe
          ref={iframeRef}
          src={url}
          title="内置浏览器"
          className="h-full w-full border-0"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
          onLoad={() => setLoading(false)}
          onError={() => { setLoading(false); setError(true); }}
        />
      </div>
    </div>
  );
}

/* ================================================================== */
/*  任务 Tab — 紧凑看板                                                */
/* ================================================================== */

function TasksTab() {
  const { tasks, activeTask } = useShellDerivedState();

  const statusMap: Record<string, { label: string; dot: string }> = {
    running: { label: "运行中", dot: "bg-amber-400" },
    done: { label: "已完成", dot: "bg-emerald-400" },
    attention: { label: "需关注", dot: "bg-red-400" },
    idle: { label: "空闲", dot: "bg-neutral-600" },
    queued: { label: "排队中", dot: "bg-blue-400" },
  };

  return (
    <div className="xagent-scrollbar h-full overflow-auto px-3 py-3">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[12px] font-medium text-neutral-300">任务列表</span>
        <Link
          to="/goal-board"
          className="flex items-center gap-1 text-[11px] text-neutral-600 transition hover:text-neutral-400"
        >
          看板视图
          <ChevronRight size={11} />
        </Link>
      </div>

      {tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <KanbanSquare size={24} className="text-neutral-800" />
          <span className="mt-2 text-[12px] text-neutral-700">暂无任务</span>
        </div>
      )}

      <div className="space-y-1.5">
        {tasks.map((task) => {
          const st = statusMap[task.status] || statusMap.idle;
          const isActive = activeTask?.id === task.id;
          return (
            <Link
              key={task.id}
              to={task.route}
              className={`block rounded-lg border px-3 py-2.5 transition ${
                isActive
                  ? "border-white/[0.1] bg-white/[0.05]"
                  : "border-white/[0.04] bg-white/[0.02] hover:bg-white/[0.04]"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${st.dot}`} />
                <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-neutral-200">
                  {task.title}
                </span>
                <span className="shrink-0 text-[10px] text-neutral-700">{st.label}</span>
              </div>
              {task.subtitle && (
                <div className="mt-1 truncate pl-3.5 text-[11px] text-neutral-600">{task.subtitle}</div>
              )}
              {task.badge && (
                <span className="mt-1.5 ml-3.5 inline-block rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-neutral-500">
                  {task.badge}
                </span>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

/* ================================================================== */
/*  动态 Tab — 活动流                                                  */
/* ================================================================== */

function ActivityTab() {
  const { activity, session } = useShellDerivedState();

  const toneIcon = (tone: string) => {
    if (tone === "success") return <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-emerald-500" />;
    if (tone === "error") return <XCircle size={13} className="mt-0.5 shrink-0 text-red-400" />;
    if (tone === "warning") return <Clock3 size={13} className="mt-0.5 shrink-0 text-amber-400" />;
    return <Activity size={13} className="mt-0.5 shrink-0 text-blue-400" />;
  };

  return (
    <div className="xagent-scrollbar h-full overflow-auto px-3 py-3">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[12px] font-medium text-neutral-300">最近动态</span>
        <span className="text-[10px] text-neutral-700">
          会话 {formatTime(session.startedAt)}
        </span>
      </div>

      {activity.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Clock3 size={24} className="text-neutral-800" />
          <span className="mt-2 text-[12px] text-neutral-700">暂无动态</span>
        </div>
      )}

      <div className="space-y-1">
        {activity.slice(0, 30).map((item) => (
          <div
            key={item.id}
            className="flex gap-2.5 rounded-lg px-2.5 py-2 transition hover:bg-white/[0.03]"
          >
            {toneIcon(item.tone)}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-[12px] text-neutral-300">{item.title}</span>
                <span className="shrink-0 text-[10px] tabular-nums text-neutral-700">
                  {formatTime(item.timestamp)}
                </span>
              </div>
              {item.detail && (
                <div className="mt-0.5 truncate text-[11px] text-neutral-600">{item.detail}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
