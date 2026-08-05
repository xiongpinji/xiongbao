import { Link, useNavigate } from "react-router-dom";
import { GitCompareArrows, PackageSearch, ShieldCheck } from "lucide-react";
import ConversationalCommand from "../components/chat/ConversationalCommand";

export default function OpenSourcePage() {
  const navigate = useNavigate();

  return (
    <div className="xagent-scrollbar h-full overflow-auto bg-transparent px-4 py-6 text-neutral-100 md:px-8">
      <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center gap-6">
        <header className="border-b border-white/[0.07] pb-5">
          <div className="text-xs font-medium tracking-wide text-neutral-500">Open source scout</div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">开源补齐方案发现</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-500">
            用对话提出能力缺口，系统按功能方向查找候选仓库、比较许可证和成熟度，再转入项目任务。
          </p>
        </header>

        <ConversationalCommand
          title="开源比选助手"
          context="能力缺口 / 仓库发现 / 许可证风险 / 接入策略"
          placeholder="例如：给短剧工厂找一个可 API 调用的视频生成与剪辑链路替代方案..."
          initialAssistantMessage="告诉我你要补齐的能力，我会先按功能、许可证、成熟度和接入方式拆分比选。"
          suggestions={[
            "打开开源发现配置",
            "比较 LangGraph 与 DeerFlow 2.0",
            "找 LiblibTV 替代 API 方案",
          ]}
          onSubmit={(value) => {
            if (value.includes("配置") || value.includes("打开")) {
              navigate("/settings?section=index&tab=open-source");
              return "已切到开源发现配置。这里负责仓库源、扫描规则和许可证策略。";
            }
            if (value.includes("许可证") || value.includes("版权")) {
              return "接入策略建议优先使用 API 调用、协议隔离和适配层，避免直接复制受限源码；每个候选仓库必须记录许可证、商用限制和替代路径。";
            }
            return `已接收开源比选目标：${value}。下一步会按成熟度、社区活跃度、许可证、API 可集成性生成对比清单。`;
          }}
        />

        <section className="grid gap-3 md:grid-cols-3">
          {[
            { icon: PackageSearch, title: "仓库发现", text: "按功能方向检索候选项目，不只看基础 demo。" },
            { icon: GitCompareArrows, title: "强弱对比", text: "比较架构、生态、维护状态和可商用接入成本。" },
            { icon: ShieldCheck, title: "协议隔离", text: "优先 API / 插件 / 适配层，降低源码搬运风险。" },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.title} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                <Icon size={18} className="text-neutral-300" />
                <div className="mt-3 text-sm font-semibold text-white">{item.title}</div>
                <p className="mt-2 text-xs leading-5 text-neutral-500">{item.text}</p>
              </div>
            );
          })}
        </section>

        <Link to="/settings?section=index&tab=open-source" className="rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-black transition hover:bg-white w-fit">
          进入开源发现设置
        </Link>
      </div>
    </div>
  );
}
