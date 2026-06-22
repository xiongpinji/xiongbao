import type { ReactNode } from "react";
import {
  BarChart3,
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
  | "onboarding";

const sections: { id: SettingsSection; label: string; icon: typeof Settings2 }[] = [
  { id: "general", label: "常规", icon: SlidersHorizontal },
  { id: "code-preview", label: "代码预览", icon: Code2 },
  { id: "models", label: "模型设置", icon: Server },
  { id: "skills", label: "技能", icon: Sparkles },
  { id: "mcp", label: "MCP 服务器", icon: PlugZap },
  { id: "plugins", label: "插件管理", icon: Box },
  { id: "commands", label: "命令", icon: Command },
  { id: "index", label: "索引库", icon: Database },
  { id: "usage", label: "使用统计", icon: BarChart3 },
  { id: "onboarding", label: "引导", icon: Rocket },
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
  return (
    <div className="flex min-h-full bg-neutral-950 text-neutral-100">
      <aside className="w-72 shrink-0 border-r border-neutral-800 bg-neutral-900 p-4">
        <a href="/chat" className="mb-6 block text-sm text-neutral-500 hover:text-white">
          ← 返回工作区
        </a>
        <div className="mb-4 px-2">
          <h1 className="text-lg font-semibold text-white">设置</h1>
          <p className="mt-1 text-xs leading-5 text-neutral-500">模型、技能、索引库与工作台偏好</p>
        </div>
        <nav className="space-y-1">
          {sections.map((section) => {
            const Icon = section.icon;
            const active = section.id === activeSection;
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => onSectionChange(section.id)}
                className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition-colors ${
                  active
                    ? "bg-neutral-700 text-white"
                    : "text-neutral-400 hover:bg-neutral-800 hover:text-white"
                }`}
              >
                <Icon size={18} strokeWidth={1.8} />
                <span>{section.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <section className="min-w-0 flex-1 overflow-auto p-8">{children}</section>
    </div>
  );
}
