import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, CheckCircle2, LockKeyhole, Plus, Search, Sparkles } from "lucide-react";
import { listRoles, type AgentRole } from "../api";
import ConversationalCommand from "../components/chat/ConversationalCommand";

export default function AgentsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const [selectedName, setSelectedName] = useState<string | null>(null);

  if (isLoading) {
    return <div className="flex h-full items-center justify-center text-sm text-neutral-500">正在加载智能体角色...</div>;
  }

  const roles: AgentRole[] = data ?? [];
  const selected = roles.find((role) => role.name === selectedName) ?? roles[0] ?? null;
  const capabilities = selected?.capabilities ?? [];

  return (
    <div className="flex h-full min-h-0 bg-transparent">
      <aside className="xagent-scrollbar w-80 shrink-0 overflow-auto border-r border-white/[0.07] bg-black/36 p-4 backdrop-blur-2xl">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">Agents</div>
            <h1 className="mt-2 text-2xl font-semibold text-white">智能体</h1>
          </div>
          <button className="xagent-chip flex h-9 w-9 items-center justify-center rounded-xl p-0">
            <Plus size={17} />
          </button>
        </div>

        <div className="xagent-composer-frame mb-4 flex items-center gap-2 px-3 py-2 text-neutral-500">
          <Search size={15} />
          <span className="text-sm">筛选角色、能力或任务方向</span>
        </div>

        <div className="space-y-1">
          {roles.map((role) => {
            const active = selected?.name === role.name;
            return (
              <button
                key={role.name}
                type="button"
                onClick={() => setSelectedName(role.name)}
                className={`w-full rounded-2xl px-3 py-3 text-left transition ${
                  active
                    ? "xagent-nav-active"
                    : "xagent-nav-item"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${active ? "bg-[#2b1e0d] text-[#f1c96f]" : "bg-white/[0.045] text-neutral-500"}`}>
                    <Bot size={17} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold">{role.name}</div>
                    <div className="mt-1 truncate text-xs text-neutral-600">{role.capabilities.length} 项能力</div>
                  </div>
                </div>
              </button>
            );
          })}
          {roles.length === 0 && (
            <div className="rounded-2xl border border-dashed border-white/[0.08] p-4 text-sm leading-6 text-neutral-500">
              当前没有可用智能体角色。
            </div>
          )}
        </div>
      </aside>

      <main className="xagent-scrollbar min-w-0 flex-1 overflow-auto p-6 md:p-8">
        {selected ? (
          <div className="mx-auto max-w-4xl">
            {error && (
              <div className="mb-5 rounded-2xl border border-amber-400/20 bg-amber-400/5 px-4 py-3 text-sm text-amber-200">
                后端角色接口暂不可用，当前无法加载智能体角色。
              </div>
            )}
            <div className="mb-8 border-b border-white/[0.07] pb-6">
              <div className="flex items-start justify-between gap-6">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">Agent profile</div>
                  <h2 className="mt-3 text-4xl font-semibold tracking-tight text-white">{selected.name}</h2>
                  <p className="mt-3 max-w-2xl text-sm leading-7 text-neutral-500">{selected.description}</p>
                </div>
                <button className="gold-button">
                  设为当前角色
                </button>
              </div>
            </div>

            <ConversationalCommand
              className="mb-5"
              title="角色调度"
              context={selected.name}
              placeholder={`告诉「${selected.name}」要完成什么任务...`}
              initialAssistantMessage={`当前已选择「${selected.name}」。你可以直接描述任务，我会按这个角色的能力拆成执行意图。`}
              suggestions={[
                "把短剧任务拆成导演工作流",
                "为当前项目生成执行计划",
                "检查这个角色的记忆边界",
              ]}
              onSubmit={(value) => ({
                content: `「${selected.name}」已接收任务：${value}。建议先使用 ${capabilities.slice(0, 2).join(" / ") || "基础能力"} 建立可验证步骤。`,
              })}
            />

            <div className="grid gap-4 xl:grid-cols-[1fr_280px]">
              <section className="xagent-surface-subtle p-5">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
                  <Sparkles size={17} className="text-[#d6ad62]" />
                  能力清单
                </div>
                <div className="divide-y divide-white/[0.06]">
                  {capabilities.map((capability) => (
                    <div key={capability} className="flex items-center justify-between gap-4 py-3">
                      <div>
                        <div className="text-sm font-medium text-neutral-100">{capability}</div>
                        <div className="mt-1 text-xs text-neutral-600">可在对话、工作流和专业模式中调用</div>
                      </div>
                      <CheckCircle2 size={17} className="shrink-0 text-emerald-400" />
                    </div>
                  ))}
                  {capabilities.length === 0 && (
                    <div className="py-8 text-center text-sm text-neutral-500">暂无能力标签。</div>
                  )}
                </div>
              </section>

              <section className="space-y-4">
                <div className="xagent-surface-subtle p-5">
                  <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
                    <LockKeyhole size={16} className="text-[#d6ad62]" />
                    记忆隔离
                  </div>
                  <p className="text-sm leading-6 text-neutral-500">
                    当前角色使用专属上下文槽位，避免跨智能体污染长期记忆。
                  </p>
                  <div className="mt-4 rounded-2xl border border-emerald-400/15 bg-emerald-400/5 px-3 py-2 text-xs text-emerald-300">
                    已启用隔离策略
                  </div>
                </div>
                <div className="xagent-surface-subtle p-5">
                  <div className="text-sm font-semibold text-white">接入位置</div>
                  <div className="mt-3 space-y-2 text-sm text-neutral-500">
                    <div>对话：可直接作为执行角色</div>
                    <div>工作流：可绑定到节点</div>
                    <div>短剧工厂：可作为导演/编剧/剪辑角色</div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-neutral-500">请选择或创建一个智能体。</div>
        )}
      </main>
    </div>
  );
}
