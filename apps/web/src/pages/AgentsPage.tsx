import { useQuery } from "@tanstack/react-query";
import { listRoles, type AgentRole } from "../api";

const fallbackRoles: AgentRole[] = [
  {
    name: "导演智能体",
    description: "负责把目标拆成剧本、分镜、镜头、生成和剪辑的协作任务。",
    capabilities: ["任务拆解", "分镜审查", "短剧导演", "质量评估"],
  },
  {
    name: "工作流编排专家",
    description: "负责把复杂目标组织成可验证、可恢复、可追踪的执行流程。",
    capabilities: ["步骤编排", "依赖管理", "审批节点", "执行复盘"],
  },
  {
    name: "记忆管理员",
    description: "负责整理长期记忆、知识库路由与跨角色信息沉淀策略。",
    capabilities: ["长期记忆", "知识沉淀", "隔离策略", "索引规划"],
  },
];

const previewMessage = "预览态：当前‘角色调度’优先生成任务拆解建议，不直接触发真实智能体执行。";
const fallbackMessage = "后端角色接口暂不可用，当前展示的是本地演示角色，仅用于 UI 预览，不代表真实可调度角色集合。";
const emptyMessage = "当前暂未收到后端角色数据，先展示本地演示角色，方便继续确认布局与说明文案。";
const executionNote = "真实执行时的角色集合、能力边界与可用性以后端返回为准。";

export default function AgentsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["roles"], queryFn: listRoles });

  if (isLoading) {
    return <div className="p-6 text-sm text-neutral-400">正在加载智能体角色...</div>;
  }

  const remoteRoles = data ?? [];
  const hasRemoteRoles = remoteRoles.length > 0;
  const roles: AgentRole[] = hasRemoteRoles ? remoteRoles : fallbackRoles;
  const helperNotice = error ? fallbackMessage : hasRemoteRoles ? null : emptyMessage;

  return (
    <div className="min-h-full bg-neutral-950 p-6 text-neutral-100 md:p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">Agent roles</div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">智能体角色</h1>
          <p className="max-w-3xl text-sm leading-6 text-neutral-400">{previewMessage}</p>
        </header>

        {helperNotice && (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-100">
            {helperNotice}
          </div>
        )}

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {roles.map((role) => (
            <article key={role.name} className="rounded-3xl border border-neutral-800 bg-neutral-900 p-5 shadow-2xl shadow-black/10">
              <div className="text-base font-semibold text-white">{role.name}</div>
              <div className="mt-2 text-sm leading-6 text-neutral-400">{role.description}</div>
              <div className="mt-4 flex flex-wrap gap-2">
                {role.capabilities.map((capability) => (
                  <span
                    key={capability}
                    className="rounded-full border border-neutral-700 bg-neutral-950 px-2.5 py-1 text-xs text-neutral-300"
                  >
                    {capability}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </section>

        <section className="rounded-2xl border border-neutral-800 bg-neutral-900/70 px-4 py-4 text-sm leading-6 text-neutral-300">
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-500">角色说明</div>
          <p className="mt-2">{executionNote}</p>
        </section>
      </div>
    </div>
  );
}
