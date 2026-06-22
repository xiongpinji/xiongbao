import { useMemo, useState } from "react";
import CodePreviewSettings from "../components/settings/CodePreviewSettings";
import CommandsSettings from "../components/settings/CommandsSettings";
import GeneralSettings from "../components/settings/GeneralSettings";
import IndexSettings, { type IndexTab } from "../components/settings/IndexSettings";
import McpServersSettings from "../components/settings/McpServersSettings";
import ModelSettings from "../components/settings/ModelSettings";
import OnboardingSettings from "../components/settings/OnboardingSettings";
import PluginSettings from "../components/settings/PluginSettings";
import SettingsLayout, { type SettingsSection } from "../components/settings/SettingsLayout";
import SkillsSettings from "../components/settings/SkillsSettings";
import UsageStatsSettings from "../components/settings/UsageStatsSettings";

export default function SettingsPage() {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const initialSection = (params.get("section") as SettingsSection | null) ?? "general";
  const initialTab = ((params.get("tab") as IndexTab | null) ?? "knowledge") as IndexTab;
  const [section, setSection] = useState<SettingsSection>(initialSection);

  return (
    <SettingsLayout activeSection={section} onSectionChange={setSection}>
      {section === "general" && <GeneralSettings />}
      {section === "code-preview" && <CodePreviewSettings />}
      {section === "models" && <ModelSettings />}
      {section === "skills" && <SkillsSettings />}
      {section === "mcp" && <McpServersSettings />}
      {section === "plugins" && <PluginSettings />}
      {section === "commands" && <CommandsSettings />}
      {section === "index" && <IndexSettings initialTab={initialTab} />}
      {section === "usage" && <UsageStatsSettings />}
      {section === "onboarding" && <OnboardingSettings />}
    </SettingsLayout>
  );
}
