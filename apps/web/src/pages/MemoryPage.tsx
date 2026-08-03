import { Link, useNavigate } from "react-router-dom";
import { Database, LockKeyhole, SearchCheck } from "lucide-react";
import ConversationalCommand from "../components/chat/ConversationalCommand";

export default function MemoryPage() {
  const navigate = useNavigate();

  return (
    <div className="xagent-scrollbar h-full overflow-auto bg-transparent px-4 py-6 text-neutral-100 md:px-8">
      <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center gap-6">
        <header className="border-b border-white/[0.06] pb-5">
          <div className="text-[11px] font-medium text-neutral-600">Memory workspace</div>
          <h1 className="mt-1.5 text-xl font-semibold tracking-tight text-neutral-100">长期记忆与知识库</h1>
          <p className="mt-2 max-w-2xl text-[12px] leading-6 text-neutral-500">
            直接描述要查找、沉淀或隔离的知识，系统会把意图路由到索引库、项目知识库和智能体专属记忆。
          </p>
        </header>

        <ConversationalCommand
          title="记忆检索助手"
          context="项目记忆 / 智能体记忆 / 知识库索引"
          placeholder="例如：查一下短剧工厂升级方案里关于 LiblibTV 替代方案的结论..."
          initialAssistantMessage="你可以直接问知识库，也可以要求我把当前信息沉淀到某个项目或智能体的专属记忆区。"
          suggestions={[
            "打开知识库配置",
            "检查智能体记忆隔离",
            "检索当前项目升级方案",
          ]}
          onSubmit={(value) => {
            if (value.includes("配置") || value.includes("打开")) {
              navigate("/settings?section=index&tab=knowledge");
              return "已切到设置里的知识库配置。这里负责索引源、记忆持久化和检索策略。";
            }
            if (value.includes("隔离")) {
              return "建议按项目、智能体、会话三层隔离：每个智能体只读自己的长期记忆，跨智能体共享内容必须先进入项目知识库并带来源标记。";
            }
            return `已接收检索意图：${value}。下一步应进入索引库查询，并把结果按项目与智能体边界回写。`;
          }}
        />

        <section className="grid gap-3 md:grid-cols-3">
          {[
            { icon: Database, title: "项目知识库", text: "长期资料、方案、交付记录统一进入项目索引。" },
            { icon: LockKeyhole, title: "智能体隔离", text: "角色记忆独立存放，避免跨角色上下文污染。" },
            { icon: SearchCheck, title: "可追溯检索", text: "检索结果保留来源、时间和命中上下文。" },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.title} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 transition-colors hover:border-white/[0.12]">
                <Icon size={16} className="text-neutral-400" />
                <div className="mt-3 text-[13px] font-medium text-neutral-200">{item.title}</div>
                <p className="mt-1.5 text-[11px] leading-5 text-neutral-500">{item.text}</p>
              </div>
            );
          })}
        </section>

        <Link to="/settings?section=index&tab=knowledge" className="inline-flex h-9 w-fit items-center rounded-lg bg-neutral-100 px-4 text-[13px] font-medium text-black transition hover:bg-white">
          进入索引库设置
        </Link>
      </div>
    </div>
  );
}
