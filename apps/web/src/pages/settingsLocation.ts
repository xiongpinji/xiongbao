import type { IndexTab } from "../components/settings/IndexSettings";
import type { SettingsSection } from "../components/settings/SettingsLayout";

const VALID_SECTIONS: SettingsSection[] = [
  "general",
  "code-preview",
  "models",
  "skills",
  "mcp",
  "plugins",
  "commands",
  "index",
  "usage",
  "team",
  "onboarding",
];

const VALID_INDEX_TABS: IndexTab[] = ["knowledge", "open-source"];

export function resolveSettingsLocation(search: string) {
  const params = new URLSearchParams(search);
  const rawSection = params.get("section");
  const rawTab = params.get("tab");

  const section = VALID_SECTIONS.includes(rawSection as SettingsSection)
    ? (rawSection as SettingsSection)
    : "general";
  const tab = VALID_INDEX_TABS.includes(rawTab as IndexTab)
    ? (rawTab as IndexTab)
    : "knowledge";

  return { section, tab };
}
