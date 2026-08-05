import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSkill, deleteSkill, listSkills, retireSkill, restoreSkill,
  retireLowPerformers, skillStats,
  type SkillView, type SkillStats,
} from "../../api";
import { SectionTitle } from "./GeneralSettings";
import { useConfirm } from "../../hooks/useConfirm";

const SOURCE_LABELS: Record<string, string> = {
  manual: "手动",
  auto_extracted: "自动提炼",
  evolved: "演化",
};

export default function SkillsSettings() {
  const [skills, setSkills] = useState<SkillView[]>([]);
  const [stats, setStats] = useState<SkillStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [showRetired, setShowRetired] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", trigger_pattern: "", tags: "" });
  const errTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { confirm, ConfirmDialog } = useConfirm();

  const showError = (msg: string) => {
    setError(msg);
    if (errTimer.current) clearTimeout(errTimer.current);
    errTimer.current = setTimeout(() => setError(null), 6000);
  };

  const refresh = useCallback(async () => {
    try {
      const [data, st] = await Promise.all([listSkills(showRetired), skillStats()]);
      setSkills(data);
      setStats(st);
      setError(null);
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    }
  }, [showRetired]);

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
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    const ok = await confirm({ title: "删除技能", message: "确定永久删除该技能？此操作不可撤销。", danger: true, confirmText: "删除" });
    if (!ok) return;
    setLoading(true);
    try {
      await deleteSkill(id);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleRetire = async (id: string) => {
    setLoading(true);
    try {
      await retireSkill(id);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async (id: string) => {
    setLoading(true);
    try {
      await restoreSkill(id);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleRetireLow = async () => {
    const ok = await confirm({ title: "淘汰低效技能", message: "将自动淘汰成功率低于阈值的技能，确定继续？", danger: true, confirmText: "淘汰" });
    if (!ok) return;
    setLoading(true);
    try {
      await retireLowPerformers();
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <SectionTitle title="技能系统" description="Agent 可学习、匹配和执行的自进化技能。关键词触发自动注入 system prompt。" />
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRetireLow}
            disabled={loading}
            className="rounded-lg bg-orange-500/10 px-3 py-2 text-xs font-medium text-orange-400 transition hover:bg-orange-500/20 disabled:opacity-40"
          >
            淘汰低效
          </button>
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            className="rounded-lg border border-white/10 px-4 py-2 text-sm text-neutral-300 transition hover:border-white/20 hover:text-neutral-100"
          >
            {showForm ? "取消" : "+ 新建技能"}
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { label: "活跃技能", value: stats.active, color: "text-emerald-400" },
            { label: "自动提炼", value: stats.auto_extracted, color: "text-blue-400" },
            { label: "已淘汰", value: stats.retired, color: "text-neutral-500" },
            { label: "平均成功率", value: `${Math.round(stats.avg_success_rate * 100)}%`, color: "text-neutral-200" },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-center">
              <div className={`text-lg font-semibold ${item.color}`}>{item.value}</div>
              <div className="text-[11px] text-neutral-500">{item.label}</div>
            </div>
          ))}
        </div>
      )}

      {error && <div className="rounded-lg bg-red-500/10 px-4 py-2 text-xs text-red-400">{error}</div>}

      {/* 创建表单 */}
      {showForm && (
        <div className="space-y-3 rounded-lg border border-white/[0.08] bg-white/[0.02] p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">技能名称 *</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="代码审查"
                className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-white/25"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">触发关键词（逗号分隔）</span>
              <input
                value={form.trigger_pattern}
                onChange={(e) => setForm({ ...form, trigger_pattern: e.target.value })}
                placeholder="review,审查,代码质量"
                className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-white/25"
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
              className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-white/25 resize-none"
            />
          </label>
          <label className="space-y-1 block">
            <span className="text-xs text-neutral-400">标签（逗号分隔）</span>
            <input
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="开发,质量"
              className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-white/25"
            />
          </label>
          <button
            type="button"
            onClick={handleCreate}
            disabled={loading || !form.name.trim()}
            className="rounded-lg bg-neutral-100 px-5 py-2 text-sm font-medium text-black transition hover:bg-white disabled:opacity-40"
          >
            {loading ? "创建中..." : "创建技能"}
          </button>
        </div>
      )}

      {/* 技能列表 */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-neutral-500">共 {skills.length} 个技能</span>
        <label className="flex items-center gap-2 text-xs text-neutral-400">
          <input
            type="checkbox"
            checked={showRetired}
            onChange={(e) => setShowRetired(e.target.checked)}
            className="rounded border-neutral-600"
          />
          显示已淘汰
        </label>
      </div>
      <div className="grid gap-3">
        {skills.length === 0 && (
          <div className="rounded-lg border border-dashed border-white/[0.08] p-6 text-center text-sm text-neutral-500">
            暂无技能。Agent 执行复杂任务后会自动提炼，也可手动添加。
          </div>
        )}
        {skills.map((skill) => (
          <div
            key={skill.skill_id}
            className={`rounded-lg border p-4 transition ${
              skill.retired
                ? "border-white/[0.04] bg-white/[0.01] opacity-60"
                : "border-white/[0.06] bg-white/[0.02]"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white">{skill.name}</span>
                <span className="rounded-full bg-neutral-700/50 px-1.5 py-0.5 text-[10px] text-neutral-400">
                  v{skill.version}
                </span>
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                  skill.source === "auto_extracted" ? "bg-blue-500/10 text-blue-400"
                  : skill.source === "evolved" ? "bg-purple-500/10 text-purple-400"
                  : "bg-neutral-700/50 text-neutral-400"
                }`}>
                  {SOURCE_LABELS[skill.source] || skill.source}
                </span>
                {skill.retired && (
                  <span className="rounded-full bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-400">已淘汰</span>
                )}
                {skill.tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[11px] text-neutral-400">{tag}</span>
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                {skill.retired ? (
                  <button
                    type="button"
                    onClick={() => handleRestore(skill.skill_id)}
                    disabled={loading}
                    className="rounded-lg bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-400 transition hover:bg-emerald-500/20"
                  >
                    恢复
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => handleRetire(skill.skill_id)}
                    disabled={loading}
                    className="rounded-lg bg-orange-500/10 px-2.5 py-1 text-xs text-orange-400 transition hover:bg-orange-500/20"
                  >
                    淘汰
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => handleDelete(skill.skill_id)}
                  disabled={loading}
                  className="rounded-lg bg-red-500/10 px-2.5 py-1 text-xs text-red-400 transition hover:bg-red-500/20"
                >
                  删除
                </button>
              </div>
            </div>
            {skill.description && <div className="mt-2 text-xs text-neutral-400 line-clamp-2">{skill.description}</div>}
            {skill.system_prompt_hint && (
              <div className="mt-1 text-[11px] text-neutral-500 italic">提示: {skill.system_prompt_hint}</div>
            )}
            <div className="mt-2 flex items-center gap-4 text-[11px] text-neutral-500">
              <span>触发: {skill.trigger_pattern || "—"}</span>
              <span>使用 {skill.use_count} 次</span>
              <span>成功率 {Math.round(skill.success_rate * 100)}%</span>
              {skill.steps.length > 0 && (
                <span>工具链: {skill.steps.map((s) => s.tool).join(" → ")}</span>
              )}
            </div>
          </div>
        ))}
      </div>
      <ConfirmDialog />
    </div>
  );
}
