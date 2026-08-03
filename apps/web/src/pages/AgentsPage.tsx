import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, CheckCircle2, LockKeyhole, Plus, Search, Sparkles } from "lucide-react";
import { listRoles, type AgentRole } from "../api";

export default function AgentsPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  if (isLoading) {
    return <div className="flex h-full items-center justify-center text-[13px] text-neutral-600">正在加载智能体角色...</div>;
  }

  // 完全加载失败：显示明确的错误态与重试入口，避免退化为误导性的“请选择或创建”空状态
  if (error && !data) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
        <div className="text-[13px] text-neutral-500">后端角色接口暂不可用，当前无法加载智能体角色。</div>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-black transition hover:bg-white"
        >
          重试
        </button>
      </div>
    );
  }

  const roles: AgentRole[] = data ?? [];
  const filtered = filter.trim()
    ? roles.filter((r) => r.name.toLowerCase().includes(filter.trim().toLowerCase()))
    : roles;
  const selected = roles.find((role) => role.name === selectedName) ?? roles[0] ?? null;
  const capabilities = selected?.capabilities ?? [];

  return (
    <div className="flex h-full min-h-0">
      {/* 左侧列表 */}
      <aside className="xagent-scrollbar w-72 shrink-0 overflow-auto border-r border-white/[0.05] bg-[#0f0f0f] p-3">
        <div className="mb-3 flex items-center justify-between px-1">
          <h1 className="text-[15px] font-semibold text-neutral-100">智能体</h1>
          <button
            type="button"
            title="新建角色"
            className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-200"
          >
            <Plus size={15} />
          </button>
        </div>

        {/* 筛选 */}
        <div className="mb-3 flex items-center gap-2 rounded-lg bg-white/[0.04] px-2.5 py-1.5">
          <Search size={13} className="shrink-0 text-neutral-600" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="筛选角色..."
            className="flex-1 bg-transparent text-[12px] text-neutral-200 outline-none placeholder:text-neutral-600"
            spellCheck={false}
          />
        </div>

        <div className="space-y-px">
          {filtered.map((role) => {
            const active = selected?.name === role.name;
            return (
              <button
                key={role.name}
                type="button"
                onClick={() => setSelectedName(role.name)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition ${
                  active ? "bg-white/[0.07]" : "hover:bg-white/[0.04]"
                }`}
              >
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                    active ? "bg-white/[0.08] text-neutral-100" : "bg-white/[0.04] text-neutral-500"
                  }`}
                >
                  <Bot size={15} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className={`truncate text-[13px] ${active ? "font-medium text-neutral-100" : "text-neutral-300"}`}>
                    {role.name}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-neutral-600">{role.capabilities.length} 项能力</div>
                </div>
              </button>
            );
          })}
          {filtered.length === 0 && (
            <div className="rounded-lg border border-dashed border-white/[0.06] p-4 text-center text-[12px] text-neutral-600">
              没有匹配的角色
            </div>
          )}
        </div>
      </aside>

      {/* 右侧详情 */}
      <main className="xagent-scrollbar min-w-0 flex-1 overflow-auto p-6 md:p-8">
        {selected ? (
          <div className="mx-auto max-w-3xl">
            {error && (
              <div className="mb-5 rounded-lg border border-amber-400/15 bg-amber-400/5 px-3.5 py-2.5 text-[12px] text-amber-200">
                后端角色接口暂不可用，当前无法加载智能体角色。
              </div>
            )}

            {/* 头部 */}
            <div className="mb-8 border-b border-white/[0.06] pb-6">
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0">
                  <h2 className="text-2xl font-semibold tracking-tight text-neutral-100">{selected.name}</h2>
                  <p className="mt-2 max-w-2xl text-[13px] leading-6 text-neutral-500">{selected.description}</p>
                </div>
                <button
                  type="button"
                  className="shrink-0 rounded-lg bg-white px-3.5 py-2 text-[13px] font-medium text-black transition hover:bg-neutral-200 active:scale-[0.98]"
                >
                  设为当前角色
                </button>
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-[1fr_260px]">
              {/* 能力清单 */}
              <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
                <div className="mb-4 flex items-center gap-2 text-[13px] font-medium text-neutral-200">
                  <Sparkles size={15} className="text-neutral-500" />
                  能力清单
                </div>
                <div className="divide-y divide-white/[0.05]">
                  {capabilities.map((capability) => (
                    <div key={capability} className="flex items-center justify-between gap-4 py-2.5">
                      <div className="min-w-0">
                        <div className="truncate text-[13px] text-neutral-200">{capability}</div>
                        <div className="mt-0.5 text-[11px] text-neutral-600">可在对话、工作流和专业模式中调用</div>
                      </div>
                      <CheckCircle2 size={15} className="shrink-0 text-emerald-500/70" />
                    </div>
                  ))}
                  {capabilities.length === 0 && (
                    <div className="py-8 text-center text-[12px] text-neutral-600">暂无能力标签</div>
                  )}
                </div>
              </section>

              {/* 侧栏信息 */}
              <section className="space-y-4">
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
                  <div className="mb-2.5 flex items-center gap-2 text-[13px] font-medium text-neutral-200">
                    <LockKeyhole size={14} className="text-neutral-500" />
                    记忆隔离
                  </div>
                  <p className="text-[12px] leading-5 text-neutral-500">
                    当前角色使用专属上下文槽位，避免跨智能体污染长期记忆。
                  </p>
                  <div className="mt-3 rounded-md border border-emerald-400/15 bg-emerald-400/5 px-2.5 py-1.5 text-[11px] text-emerald-300">
                    已启用隔离策略
                  </div>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
                  <div className="text-[13px] font-medium text-neutral-200">接入位置</div>
                  <div className="mt-2.5 space-y-1.5 text-[12px] text-neutral-500">
                    <div>对话：可直接作为执行角色</div>
                    <div>工作流：可绑定到节点</div>
                    <div>短剧工厂：可作为导演 / 编剧 / 剪辑角色</div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[13px] text-neutral-600">请选择或创建一个智能体</div>
        )}
      </main>
    </div>
  );
}


