import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import CodePreviewSettings from "../components/settings/CodePreviewSettings";
import CommandsSettings from "../components/settings/CommandsSettings";
import GeneralSettings from "../components/settings/GeneralSettings";
import IndexSettings from "../components/settings/IndexSettings";
import KnowledgeSettings from "../components/settings/KnowledgeSettings";
import McpServersSettings from "../components/settings/McpServersSettings";
import ModelSettings from "../components/settings/ModelSettings";
import OnboardingSettings from "../components/settings/OnboardingSettings";
import PluginSettings from "../components/settings/PluginSettings";
import SettingsLayout from "../components/settings/SettingsLayout";
import SkillsSettings from "../components/settings/SkillsSettings";
import TeamSettings from "../components/settings/TeamSettings";
import UsageStatsSettings from "../components/settings/UsageStatsSettings";
import WebhookSettings from "../components/settings/WebhookSettings";
import { resolveSettingsLocation } from "./settingsLocation";

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useMemo(
    () => resolveSettingsLocation(`?${searchParams.toString()}`),
    [searchParams],
  );

  return (
    <SettingsLayout
      activeSection={location.section}
      onSectionChange={(section) => {
        const nextParams = new URLSearchParams(searchParams);
        nextParams.set("section", section);
        if (section !== "index") {
          nextParams.delete("tab");
        } else if (!nextParams.get("tab")) {
          nextParams.set("tab", "knowledge");
        }
        setSearchParams(nextParams, { replace: true });
      }}
    >
      {location.section === "general" && <GeneralSettings />}
      {location.section === "code-preview" && <CodePreviewSettings />}
      {location.section === "models" && <ModelSettings />}
      {location.section === "skills" && <SkillsSettings />}
      {location.section === "mcp" && <McpServersSettings />}
      {location.section === "plugins" && <PluginSettings />}
      {location.section === "commands" && <CommandsSettings />}
      {location.section === "index" && <IndexSettings initialTab={location.tab} />}
      {location.section === "usage" && <UsageStatsSettings />}
      {location.section === "team" && <TeamSettings />}
      {location.section === "knowledge" && <KnowledgeSettings />}
      {location.section === "webhook" && <WebhookSettings />}
      {location.section === "onboarding" && <OnboardingSettings />}
    </SettingsLayout>
  );
}
