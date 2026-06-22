import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Folder, PanelLeftClose, PanelLeftOpen, Search, Settings, SlidersHorizontal } from "lucide-react";

const projects = [
  {
    name: "xiong bao",
    tasks: ["前端 UI 重构自由画布", "短剧工厂工作流", "ZCode 工作台骨架"],
  },
  { name: "X-Agent", tasks: ["项目总览更新", "工作流对齐"] },
  { name: "ZCodeProject", tasks: ["暂无任务"] },
];

const settingsShortcuts = [
  { label: "常规", section: "general" },
  { label: "模型设置", section: "models" },
  { label: "技能", section: "skills" },
  { label: "索引库", section: "index" },
  { label: "使用统计", section: "usage" },
];

export default function WorkspaceSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  if (collapsed) {
    return (
      <button
        type="button"
        title="展开工作区"
        onClick={onToggle}
        className="flex h-screen w-9 shrink-0 items-start justify-center border-r border-neutral-800 bg-neutral-900 pt-4 text-neutral-500 hover:text-white"
      >
        <PanelLeftOpen size={18} />
      </button>
    );
  }

  return (
    <aside className="flex h-screen w-80 shrink-0 flex-col border-r border-neutral-800 bg-neutral-900 text-neutral-200">
      <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-white">工作区</div>
          <div className="text-xs text-neutral-500">项目、任务与对话上下文</div>
        </div>
        <button
          type="button"
          title="折叠工作区"
          onClick={onToggle}
          className="rounded-lg p-2 text-neutral-500 hover:bg-neutral-800 hover:text-white"
        >
          <PanelLeftClose size={17} />
        </button>
      </div>

      <div className="space-y-2 border-b border-neutral-800 p-3">
        <button className="flex w-full items-center justify-between rounded-xl bg-neutral-800 px-3 py-2 text-left text-sm text-white hover:bg-neutral-700">
          <span>新建任务</span>
          <span className="text-xs text-neutral-500">Ctrl+N</span>
        </button>
        <button className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white">
          <span className="flex items-center gap-2"><Search size={15} />搜索</span>
          <span className="text-xs text-neutral-500">Ctrl+K</span>
        </button>
        <button className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white">
          <SlidersHorizontal size={15} />技能
        </button>
      </div>

      <div className="flex-1 overflow-auto p-3">
        <div className="mb-2 text-xs font-medium text-neutral-500">项目库</div>
        <div className="space-y-3">
          {projects.map((project) => (
            <div key={project.name}>
              <div className="mb-1 flex items-center gap-2 px-2 text-sm font-medium text-neutral-400">
                <Folder size={15} /> {project.name}
              </div>
              <div className="space-y-1 pl-4">
                {project.tasks.map((task, index) => (
                  <div
                    key={task}
                    className={`rounded-xl px-3 py-2 text-sm ${
                      index === 0 && project.name === "xiong bao"
                        ? "bg-neutral-700 text-white"
                        : "text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
                    }`}
                  >
                    <div className="truncate">{task}</div>
                    <div className="mt-1 text-xs text-neutral-600">{index + 3} 分钟</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <UserRow />
    </aside>
  );
}

function UserRow() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    function handler(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={rootRef} className="relative border-t border-neutral-800 p-3">
      <div className="flex items-center justify-between rounded-xl bg-neutral-950 px-3 py-2">
        <div>
          <div className="text-sm font-semibold text-white">Xiongpinji</div>
          <div className="text-xs text-neutral-500">当前用户</div>
        </div>
        <button
          type="button"
          title="设置"
          onClick={() => setOpen((value) => !value)}
          className={`rounded-lg p-2 transition-colors ${open ? "bg-neutral-800 text-white" : "text-neutral-500 hover:bg-neutral-800 hover:text-white"}`}
        >
          <Settings size={17} />
        </button>
      </div>

      {open && (
        <div className="absolute bottom-16 left-3 z-30 w-60 rounded-2xl border border-neutral-700 bg-neutral-900 p-1 shadow-2xl shadow-black/40">
          {settingsShortcuts.map((item) => (
            <button
              key={item.section}
              type="button"
              onClick={() => {
                setOpen(false);
                navigate(`/settings?section=${item.section}`);
              }}
              className="block w-full rounded-xl px-3 py-2 text-left text-sm text-neutral-200 hover:bg-neutral-800 hover:text-white"
            >
              {item.label}
            </button>
          ))}
          <div className="my-1 h-px bg-neutral-800" />
          <Link
            to="/settings"
            onClick={() => setOpen(false)}
            className="block w-full rounded-xl px-3 py-2 text-left text-sm text-white hover:bg-neutral-800"
          >
            打开设置中心
          </Link>
        </div>
      )}
    </div>
  );
}
