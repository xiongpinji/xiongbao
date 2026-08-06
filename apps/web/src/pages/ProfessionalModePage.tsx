import { Code2, Workflow } from "lucide-react";
import WorkflowsPage from "./WorkflowsPage";

export default function ProfessionalModePage() {
  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent text-neutral-100">
      <header className="shrink-0 border-b border-white/[0.07] bg-black/32 px-4 py-3 backdrop-blur-lg">
        <div className="flex items-center gap-3">
          <div className="hidden min-w-44 items-center gap-3 lg:flex">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/[0.07] bg-white/[0.04] text-neutral-300">
              <Code2 size={18} />
            </span>
            <div>
              <div className="text-sm font-semibold text-white">专业模式</div>
              <div className="text-xs text-neutral-500">Studio command center</div>
            </div>
          </div>

          <div className="flex min-w-0 flex-1 items-center gap-3 rounded-lg border border-white/[0.12] bg-white/[0.06] px-3 py-2.5 text-white">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/[0.14] bg-white/[0.06]">
              <Workflow size={18} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">工作流</span>
              <span className="mt-1 block truncate text-xs text-neutral-500">
                步骤编排、依赖、执行与审批
              </span>
            </span>
          </div>
        </div>
      </header>

      <section className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <WorkflowsPage />
      </section>
    </div>
  );
}
