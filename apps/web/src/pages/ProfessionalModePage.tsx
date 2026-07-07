import { Link, Navigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Code2, Film, Scissors, Workflow, type LucideIcon } from "lucide-react";
import WorkflowsPage from "./WorkflowsPage";

type ProfessionalMode = "drama" | "workflow";

interface ModeItem {
  id: ProfessionalMode;
  label: string;
  description: string;
  icon: LucideIcon;
}

const modes: ModeItem[] = [
  {
    id: "drama",
    label: "短剧工厂",
    description: "剧本、分镜、媒体生成、剪辑深链",
    icon: Film,
  },
  {
    id: "workflow",
    label: "工作流",
    description: "步骤编排、依赖、执行与审批",
    icon: Workflow,
  },
];

function resolveMode(value: string | null): ProfessionalMode {
  return value === "workflow" ? "workflow" : "drama";
}

function hrefFor(mode: ProfessionalMode, workspaceId: string | null) {
  if (mode === "drama") return "/creative/canvas";
  const params = new URLSearchParams({ mode });
  if (mode === "workflow" && workspaceId) params.set("workspace", workspaceId);
  return `/professional?${params.toString()}`;
}

export default function ProfessionalModePage() {
  const [searchParams] = useSearchParams();
  const activeMode = resolveMode(searchParams.get("mode"));
  const workspaceId = searchParams.get("workspace");

  if (activeMode === "drama") {
    return <Navigate to="/creative/canvas" replace />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent text-neutral-100">
      <header className="shrink-0 border-b border-white/[0.07] bg-black/32 px-4 py-3 backdrop-blur-2xl">
        <div className="flex items-center gap-3">
          <div className="hidden min-w-44 items-center gap-3 lg:flex">
            <span className="xagent-icon-tile h-10 w-10">
              <Code2 size={18} />
            </span>
            <div>
              <div className="text-sm font-semibold text-white">专业模式</div>
              <div className="text-xs text-neutral-500">Studio command center</div>
            </div>
          </div>

          <nav className="xagent-scrollbar flex min-w-0 flex-1 gap-2 overflow-x-auto">
          {modes.map((mode) => {
            const Icon = mode.icon;
            const active = mode.id === activeMode;
            return (
              <Link
                key={mode.id}
                to={hrefFor(mode.id, workspaceId)}
                className={`group flex min-w-[220px] items-center gap-3 rounded-2xl px-3 py-2.5 transition ${
                  active
                    ? "xagent-nav-active"
                    : "xagent-nav-item"
                }`}
              >
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${
                  active ? "border-[#8a6a32]/45 bg-[#21180c]" : "border-white/[0.07] bg-black/25"
                }`}>
                  <Icon size={18} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{mode.label}</span>
                  <span className="mt-1 block truncate text-xs text-neutral-500">{mode.description}</span>
                </span>
                <ArrowRight size={14} className="shrink-0 opacity-40 transition group-hover:translate-x-0.5 group-hover:opacity-80" />
              </Link>
            );
          })}
          </nav>

          <Link
            to="/editor"
            className="xagent-chip hidden shrink-0 items-center gap-2 rounded-2xl px-3 py-2 text-sm md:flex"
          >
            <Scissors size={17} />
            高级剪辑
            <ArrowRight size={14} />
          </Link>
        </div>
      </header>

      <section className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <WorkflowsPage />
      </section>
    </div>
  );
}
