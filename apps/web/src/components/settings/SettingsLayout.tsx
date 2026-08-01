import type { ReactNode } from "react";
import {
  BarChart3,
  Bell,
  BookOpen,
  Box,
  Code2,
  Command,
  Database,
  PlugZap,
  Rocket,
  Server,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Users,
} from "lucide-react";
import ConversationalCommand from "../chat/ConversationalCommand";

export type SettingsSection =
  | "general"
  | "code-preview"
  | "models"
  | "skills"
  | "mcp"
  | "plugins"
  | "commands"
  | "index"
  | "usage"
  | "team"
  | "knowledge"
  | "webhook"
  | "onboarding";

const sections: { id: SettingsSection; label: string; description: string; icon: typeof Settings2 }[] = [
  { id: "general", label: "常规", description: "访问、会话与工作台基础偏好", icon: SlidersHorizontal },
  { id: "code-preview", label: "代码预览", description: "代码查看、差异与预览行为", icon: Code2 },
  { id: "models", label: "模型设置", description: "模型、媒体生成与调用能力", icon: Server },
  { id: "skills", label: "技能", description: "本地技能、角色能力与执行入口", icon: Sparkles },
  { id: "mcp", label: "MCP 服务器", description: "外部工具网关与 server 配置", icon: PlugZap },
  { id: "plugins", label: "插件管理", description: "插件、工具与能力注册状态", icon: Box },
  { id: "commands", label: "命令", description: "Slash 命令与快捷执行入口", icon: Command },
  { id: "index", label: "索引库", description: "知识库、记忆检索和候选发现", icon: Database },
  { id: "usage", label: "使用统计", description: "运行、产物与资源使用数据", icon: BarChart3 },
  { id: "team", label: "团队管理", description: "用户、角色与 API Key 管理", icon: Users },
  { id: "knowledge", label: "知识库", description: "RAG 文档管理与语义检索", icon: BookOpen },
  { id: "webhook", label: "Webhook & 安全", description: "通知回调与内容安全扫描", icon: Bell },
  { id: "onboarding", label: "引导", description: "快速上手和工作区初始化", icon: Rocket },
];

export default function SettingsLayout({
  activeSection,
  onSectionChange,
  children,
}: {
  activeSection: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  children: ReactNode;
}) {
  const active = sections.find((section) => section.id === activeSection) ?? sections[0];

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent text-neutral-100 lg:flex-row">
      <aside className="xagent-scrollbar w-full shrink-0 overflow-auto border-b border-white/[0.07] bg-black/38 p-4 backdrop-blur-2xl lg:h-full lg:w-72 lg:border-b-0 lg:border-r">
        <a href="/chat" className="xagent-nav-item mb-6 block px-3 py-2 text-sm">
          返回工作区
        </a>
        <div className="mb-4 px-2">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">Settings</div>
          <h1 className="mt-2 text-2xl font-semibold text-white">设置</h1>
          <p className="mt-2 text-xs leading-5 text-neutral-500">模型、技能、索引库与工作台偏好</p>
        </div>
        <nav className="flex gap-2 overflow-x-auto pb-1 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
          {sections.map((section) => {
            const Icon = section.icon;
            const active = section.id === activeSection;
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => onSectionChange(section.id)}
                className={`flex min-w-max items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition-colors lg:w-full ${
                  active
                    ? "xagent-nav-active"
                    : "xagent-nav-item"
                }`}
              >
                <Icon size={18} strokeWidth={1.8} />
                <span>{section.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <section className="xagent-scrollbar min-h-0 min-w-0 flex-1 overflow-auto">
        <div className="border-b border-white/[0.07] bg-black/15 px-5 py-5 backdrop-blur lg:px-8 lg:py-6">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">Configuration</div>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-white">{active.label}</h2>
          <p className="mt-2 text-sm leading-6 text-neutral-500">{active.description}</p>
        </div>
        <div className="settings-pane mx-auto max-w-5xl space-y-6 px-5 py-6 lg:px-8 lg:py-7">
          {children}
          <ConversationalCommand
            title="配置助手"
            context={`设置 / ${active.label}`}
            placeholder={`描述你想如何调整「${active.label}」...`}
            initialAssistantMessage={`你可以直接告诉我想怎么配置「${active.label}」，我会把自然语言转成可执行的配置检查清单。`}
            suggestions={[
              "检查当前配置缺口",
              "给我推荐最稳妥设置",
              "把这项配置转成交付任务",
            ]}
            onSubmit={(value) => ({
              content: `已记录配置意图：「${value}」。下一步会优先核对当前 ${active.label} 配置、风险和需要验证的项。`,
            })}
          />
        </div>
      </section>
    </div>
  );
}
