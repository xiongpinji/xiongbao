import { useCallback, useEffect, useState } from "react";
import { createSkill, deleteSkill, listSkills, type SkillView } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function SkillsSettings() {
  const [skills, setSkills] = useState<SkillView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", trigger_pattern: "", tags: "" });

  const refresh = useCallback(async () => {
    try {
      const data = await listSkills();
      setSkills(data);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    setLoading(true);
    try {
      await createSkill({
        name: form.name.trim(),
        description: form.description.trim(),
        trigger_pattern: form.trigger_pattern.trim(),
        tags: form.tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
      });
      setForm({ name: "", description: "", trigger_pattern: "", tags: "" });
      setShowForm(false);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    setLoading(true);
    try {
      await deleteSkill(id);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <SectionTitle title="技能系统" description="Agent 可学习、匹配和执行的自进化技能。关键词触发自动注入 system prompt。" />
        <button
          type="button"
          onClick={() => setShowForm(!showForm)}
          className="rounded-xl bg-[#d6ad62]/15 px-4 py-2 text-sm font-medium text-[#d6ad62] transition hover:bg-[#d6ad62]/25"
        >
          {showForm ? "取消" : "+ 新建技能"}
        </button>
      </div>

      {error && <div className="rounded-xl bg-red-500/10 px-4 py-2 text-xs text-red-400">{error}</div>}

      {/* 创建表单 */}
      {showForm && (
        <div className="space-y-3 rounded-2xl border border-neutral-700 bg-neutral-900/80 p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">技能名称 *</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="代码审查"
                className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-[#d6ad62]"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">触发关键词（逗号分隔）</span>
              <input
                value={form.trigger_pattern}
                onChange={(e) => setForm({ ...form, trigger_pattern: e.target.value })}
                placeholder="review,审查,代码质量"
                className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-[#d6ad62]"
              />
            </label>
          </div>
          <label className="space-y-1 block">
            <span className="text-xs text-neutral-400">描述 / 执行指令</span>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="当用户要求代码审查时，按以下流程执行..."
              rows={3}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-[#d6ad62] resize-none"
            />
          </label>
          <label className="space-y-1 block">
            <span className="text-xs text-neutral-400">标签（逗号分隔）</span>
            <input
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="开发,质量"
              className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-[#d6ad62]"
            />
          </label>
          <button
            type="button"
            onClick={handleCreate}
            disabled={loading || !form.name.trim()}
            className="rounded-xl bg-[#d6ad62] px-5 py-2 text-sm font-medium text-black transition hover:bg-[#e0be7a] disabled:opacity-40"
          >
            {loading ? "创建中..." : "创建技能"}
          </button>
        </div>
      )}

      {/* 技能列表 */}
      <div className="grid gap-3">
        {skills.length === 0 && (
          <div className="rounded-2xl border border-dashed border-neutral-700 p-6 text-center text-sm text-neutral-500">
            暂无技能。Agent 执行任务时可通过 skill_create 工具自主创建，也可手动添加。
          </div>
        )}
        {skills.map((skill) => (
          <div key={skill.skill_id} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-white">{skill.name}</span>
                {skill.tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-[#d6ad62]/10 px-2 py-0.5 text-[11px] text-[#d6ad62]">{tag}</span>
                ))}
              </div>
              <button
                type="button"
                onClick={() => handleDelete(skill.skill_id)}
                disabled={loading}
                className="rounded-lg bg-red-500/10 px-2.5 py-1 text-xs text-red-400 transition hover:bg-red-500/20"
              >
                删除
              </button>
            </div>
            {skill.description && <div className="mt-2 text-xs text-neutral-400 line-clamp-2">{skill.description}</div>}
            <div className="mt-2 flex items-center gap-4 text-[11px] text-neutral-500">
              <span>触发: {skill.trigger_pattern || "—"}</span>
              <span>使用 {skill.use_count} 次</span>
              <span>成功率 {Math.round(skill.success_rate * 100)}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
