import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  BookOpen,
  Box,
  Code2,
  Command,
  Database,
  PlugZap,
  Server,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Users,
} from "lucide-react";

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

const sections: { id: SettingsSection; label: string; icon: typeof Settings2 }[] = [
  { id: "general", label: "常规", icon: SlidersHorizontal },
  { id: "models", label: "模型", icon: Server },
  { id: "skills", label: "技能", icon: Sparkles },
  { id: "mcp", label: "MCP 服务", icon: PlugZap },
  { id: "plugins", label: "插件", icon: Box },
  { id: "commands", label: "命令", icon: Command },
  { id: "code-preview", label: "代码预览", icon: Code2 },
  { id: "index", label: "索引", icon: Database },
  { id: "knowledge", label: "知识库", icon: BookOpen },
  { id: "usage", label: "用量", icon: BarChart3 },
  { id: "team", label: "团队", icon: Users },
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
  const navigate = useNavigate();

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      {/* 左侧导航 */}
      <aside className="xagent-scrollbar w-full shrink-0 overflow-auto border-b border-white/[0.05] p-3 lg:h-full lg:w-52 lg:border-b-0 lg:border-r">
        <button
          type="button"
          onClick={() => navigate("/chat")}
          className="mb-4 flex items-center gap-1.5 px-2 py-1.5 text-[12px] text-neutral-500 transition hover:text-neutral-300"
        >
          <ArrowLeft size={12} />
          返回
        </button>
        <nav className="flex gap-1 overflow-x-auto pb-1 lg:block lg:space-y-px lg:overflow-visible lg:pb-0">
          {sections.map((section) => {
            const Icon = section.icon;
            const active = section.id === activeSection;
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => onSectionChange(section.id)}
                className={`flex min-w-max items-center gap-2 rounded-md px-2.5 py-2 text-left text-[13px] transition lg:w-full ${
                  active
                    ? "bg-white/[0.06] text-neutral-100"
                    : "text-neutral-500 hover:bg-white/[0.03] hover:text-neutral-300"
                }`}
              >
                <Icon size={14} className="shrink-0 opacity-60" />
                <span>{section.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* 右侧内容 */}
      <section className="xagent-scrollbar min-h-0 min-w-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          {children}
        </div>
      </section>
    </div>
  );
}
