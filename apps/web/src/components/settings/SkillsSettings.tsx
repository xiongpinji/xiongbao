import { useEffect, useState } from "react";
import { listRoles, type AgentRole } from "../../api";
import { SectionTitle } from "./GeneralSettings";

const localSkills = [
  "design-taste-frontend",
  "redesign-existing-projects",
  "minimalist-ui",
  "full-output-enforcement",
];

export default function SkillsSettings() {
  const [roles, setRoles] = useState<AgentRole[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRoles()
      .then(setRoles)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="max-w-4xl space-y-8">
      <SectionTitle title="技能" description="管理本地前端技能与后端 agent 角色能力。" />

      <section className="space-y-3">
        <div className="text-sm font-medium text-neutral-300">前端品味技能（tasteskill）</div>
        <div className="grid gap-3">
          {localSkills.map((skill) => (
            <div key={skill} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
              <div className="text-sm font-medium text-white">{skill}</div>
              <div className="mt-1 text-xs text-neutral-500">项目级 tasteskill，位于 .agents/skills。</div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="text-sm font-medium text-neutral-300">Agent 角色</div>
        {error && <div className="text-xs text-red-400">{error}</div>}
        <div className="grid gap-3 md:grid-cols-2">
          {roles.map((role) => (
            <div key={role.name} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
              <div className="text-sm font-medium text-white">{role.name}</div>
              <div className="mt-1 text-xs text-neutral-500">能力：{role.capabilities.join(", ") || "—"}</div>
              <div className="mt-2 text-xs text-neutral-400">{role.description}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
