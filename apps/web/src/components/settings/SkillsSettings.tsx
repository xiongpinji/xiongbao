import { useCallback, useEffect, useRef, useState } from "react";
import {
  approveEvolution, createSkill, deleteSkill, evolveAutoSkill, importSkillMd,
  disableSkill, enableSkill, listPendingEvolutions, listSkills, rejectEvolution, retireSkill, restoreSkill,
  retireLowPerformers, skillStats,
  type PendingEvolution, type SkillView, type SkillStats,
} from "../../api";
import {
  importSkillPackage,
  listSkillPackages,
  shortSkillPackageHash,
  skillPackageFilePaths,
  type SkillPackageView,
} from "../../api/skillPackages";
import { btnDanger, btnGhost, btnOk, btnPrimary, btnWarn, SectionHeader, StatLine } from "./ui";
import { useConfirm } from "../../hooks/useConfirm";

const SOURCE_LABELS: Record<string, string> = {
  manual: "手动",
  auto_extracted: "自动提炼",
  auto_distilled: "自动提炼",
  failure_distilled: "失败反思",
  evolved: "演化",
  import: "导入",
  package_import: "技能包",
};

export default function SkillsSettings() {
  const [skills, setSkills] = useState<SkillView[]>([]);
  const [stats, setStats] = useState<SkillStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [packageFile, setPackageFile] = useState<File | null>(null);
  const [packages, setPackages] = useState<SkillPackageView[]>([]);
  const [pending, setPending] = useState<PendingEvolution[]>([]);
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
      const [data, st, pe, packageData] = await Promise.all([
        listSkills(showRetired), skillStats(), listPendingEvolutions(), listSkillPackages(),
      ]);
      setSkills(data);
      setStats(st);
      setPending(pe.pending);
      setPackages(packageData);
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

  const handleToggleEnabled = async (id: string, next: boolean) => {
    setLoading(true);
    try {
      if (next) await enableSkill(id);
      else await disableSkill(id);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    if (!importText.trim()) return;
    setLoading(true);
    try {
      const res = await importSkillMd(importText);
      if (!res.imported) {
        showError(`导入被门禁拒绝: ${res.reason || "未知原因"}`);
        return;
      }
      setImportText("");
      setShowImport(false);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handlePackageImport = async () => {
    if (!packageFile) return;
    setLoading(true);
    try {
      await importSkillPackage(packageFile);
      setPackageFile(null);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleEvolveAuto = async (id: string) => {
    setLoading(true);
    try {
      const res = await evolveAutoSkill(id, true);
      if (res.pending_id) {
        await refresh();
      } else {
        showError(`未产生待审核变体: ${res.reason}`);
      }
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (pendingId: string) => {
    setLoading(true);
    try {
      await approveEvolution(pendingId);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (pendingId: string) => {
    const ok = await confirm({ title: "拒绝进化", message: "确定丢弃该优胜变体？技能保持现状。", danger: true, confirmText: "拒绝" });
    if (!ok) return;
    setLoading(true);
    try {
      await rejectEvolution(pendingId);
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
      <SectionHeader
        title="skills"
        desc="Agent 可学习、匹配和执行的自进化技能。关键词触发自动注入 system prompt。"
        actions={
          <>
            <button type="button" onClick={handleRetireLow} disabled={loading} className={btnWarn}>淘汰低效</button>
            <button type="button" onClick={() => { setShowImport(!showImport); setShowForm(false); }} className={btnGhost}>{showImport ? "取消" : "导入 SKILL.md"}</button>
            <button type="button" onClick={() => { setShowForm(!showForm); setShowImport(false); }} className={btnPrimary}>{showForm ? "取消" : "+ 新建技能"}</button>
          </>
        }
      />

      {/* 统计卡片 */}
      {stats && (
        <StatLine
          items={[
            { label: "活跃", value: stats.active, tone: "ok" },
            { label: "自动提炼", value: stats.auto_extracted },
            { label: "待审核进化", value: pending.length, tone: pending.length > 0 ? "warn" : "muted" },
            { label: "已淘汰", value: stats.retired, tone: "muted" },
            { label: "平均成功率", value: `${Math.round(stats.avg_success_rate * 100)}%` },
          ]}
        />
      )}

      {error && <div className="rounded-lg bg-red-500/10 px-4 py-2 text-xs text-red-400">{error}</div>}

      {/* 待审核进化队列（V3-2 人工门禁） */}
      {pending.length > 0 && (
        <div className="space-y-3 rounded-lg border border-purple-500/20 bg-purple-500/[0.04] p-5">
          <div className="text-sm font-medium text-purple-300">待审核进化（{pending.length}）</div>
          {pending.map((p) => (
            <div key={p.pending_id} className="py-2">
              <div className="flex items-center justify-between">
                <div className="text-xs text-neutral-300">
                  得分 {p.parent_eval?.score?.toFixed(2) ?? "?"} → {p.best_eval?.score?.toFixed(2) ?? "?"}
                  <span className="ml-2 text-neutral-500">{p.reason}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleApprove(p.pending_id)}
                    disabled={loading}
                    className="rounded-lg bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-400 transition hover:bg-emerald-500/20"
                  >
                    批准入库
                  </button>
                  <button
                    type="button"
                    onClick={() => handleReject(p.pending_id)}
                    disabled={loading}
                    className="rounded-lg bg-red-500/10 px-2.5 py-1 text-xs text-red-400 transition hover:bg-red-500/20"
                  >
                    拒绝
                  </button>
                </div>
              </div>
              {p.variant?.description && (
                <div className="mt-2 text-xs text-neutral-400 line-clamp-2">变体描述: {p.variant.description}</div>
              )}
              {p.variant?.trigger_pattern && (
                <div className="mt-1 text-[11px] text-neutral-500">变体触发: {p.variant.trigger_pattern}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* SKILL.md 导入表单（V3-1 生态兼容） */}
      {showImport && (
        <div className="space-y-3 p-1">
          <div className="space-y-3 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] p-4">
            <div>
              <div className="text-sm font-medium text-emerald-300">完整技能包 ZIP</div>
              <div className="mt-1 text-xs text-neutral-400">
                保留 SKILL.md、references、scripts 和 assets。脚本只存储，不会在导入时自动执行。
              </div>
            </div>
            <input
              type="file"
              accept=".zip,application/zip"
              onChange={(event) => setPackageFile(event.target.files?.[0] ?? null)}
              className="block w-full text-xs text-neutral-300 file:mr-3 file:rounded-md file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-xs file:text-neutral-200"
            />
            <button
              type="button"
              onClick={handlePackageImport}
              disabled={loading || !packageFile}
              className="rounded-md bg-white/[0.08] px-3 py-1.5 text-[12px] font-medium text-neutral-100 transition hover:bg-white/[0.14] disabled:opacity-40"
            >
              {loading ? "导入中..." : "安全校验并导入 ZIP"}
            </button>
          </div>
          <div className="border-t border-white/[0.06] pt-3 text-xs text-neutral-500">
            兼容入口：仅粘贴单个 SKILL.md，不包含 references、scripts 或 assets。
          </div>
          <div className="text-xs text-neutral-400">
            粘贴 SKILL.md 全文（agentskills.io 格式，兼容 Hermes / Claude Code 技能库）。导入强制过质量门禁：字段完整、触发可命中、去重、容量。
          </div>
          <textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={'---\nname: my-skill\ndescription: Use when ...\n---\n# 正文规程...'}
            rows={10}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 font-mono text-xs text-white outline-none transition-colors focus:border-white/25"
          />
          <button
            type="button"
            onClick={handleImport}
            disabled={loading || !importText.trim()}
            className="rounded-md bg-white/[0.08] px-3 py-1.5 text-[12px] font-medium text-neutral-100 transition hover:bg-white/[0.14] disabled:opacity-40"
          >
            {loading ? "导入中..." : "过门禁并导入"}
          </button>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-white">完整技能包</span>
          <span className="text-xs text-neutral-500">共 {packages.length} 个包</span>
        </div>
        {packages.length === 0 && (
          <div className="rounded-lg border border-dashed border-white/[0.08] p-4 text-xs text-neutral-500">
            暂无完整技能包，可从上方导入 ZIP。
          </div>
        )}
        {packages.map((pkg) => (
          <div key={pkg.package_id} className="py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white">{pkg.name}</span>
                <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300">
                  v{pkg.version}
                </span>
              </div>
              <span className="font-mono text-[11px] text-neutral-500" title={pkg.content_hash}>
                SHA-256 {shortSkillPackageHash(pkg.content_hash)}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-400">
              <span>来源：{pkg.source || "未标注"}</span>
              <span>{pkg.file_count} 个文件</span>
              <span>{pkg.total_size.toLocaleString()} bytes</span>
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-neutral-400">查看 manifest</summary>
              <div className="mt-2 space-y-1 rounded-md bg-black/20 p-3 font-mono text-[11px] text-neutral-400">
                {skillPackageFilePaths(pkg.manifest).map((path) => (
                  <div key={path}>{path}</div>
                ))}
              </div>
            </details>
          </div>
        ))}
      </div>

      {/* 创建表单 */}
      {showForm && (
        <div className="space-y-3 p-1">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">技能名称 *</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="代码审查"
                className="w-full rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">触发关键词（逗号分隔）</span>
              <input
                value={form.trigger_pattern}
                onChange={(e) => setForm({ ...form, trigger_pattern: e.target.value })}
                placeholder="review,审查,代码质量"
                className="w-full rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]"
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
              className="w-full rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2] resize-none"
            />
          </label>
          <label className="space-y-1 block">
            <span className="text-xs text-neutral-400">标签（逗号分隔）</span>
            <input
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="开发,质量"
              className="w-full rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]"
            />
          </label>
          <button
            type="button"
            onClick={handleCreate}
            disabled={loading || !form.name.trim()}
            className="rounded-md bg-white/[0.08] px-3 py-1.5 text-[12px] font-medium text-neutral-100 transition hover:bg-white/[0.14] disabled:opacity-40"
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
            className={`border-b border-white/[0.05] py-3 ${skill.retired ? "opacity-50" : ""}`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white">{skill.name}</span>
                <span className="font-mono text-[11px] text-neutral-500">v{skill.version}</span>
                <span className="font-mono text-[11px] text-neutral-500">· {SOURCE_LABELS[skill.source] || skill.source}</span>
                {skill.retired && (
                  <span className="font-mono text-[11px] text-red-400/80">· 已淘汰</span>
                )}
                {!skill.retired && skill.is_active === false && (
                  <span className="font-mono text-[11px] text-amber-400/90">· 待启用</span>
                )}
              </div>
              <div className="flex items-center gap-0.5">
                {skill.retired ? (
                  <button type="button" onClick={() => handleRestore(skill.skill_id)} disabled={loading} className={btnOk}>恢复</button>
                ) : (
                  <>
                    {skill.is_active === false && (
                      <button type="button" onClick={() => handleToggleEnabled(skill.skill_id, true)} disabled={loading} title="蒸馏技能默认停用；人工启用后才会注入到任务执行" className={btnWarn}>启用</button>
                    )}
                    {skill.is_active === true && (
                      <button type="button" onClick={() => handleToggleEnabled(skill.skill_id, false)} disabled={loading} title="停用后保留技能但不再注入任务" className={btnGhost}>停用</button>
                    )}
                    <button type="button" onClick={() => handleEvolveAuto(skill.skill_id)} disabled={loading} title="生成改进变体并评测，优胜者进待审核队列" className={btnGhost}>进化</button>
                    <button type="button" onClick={() => handleRetire(skill.skill_id)} disabled={loading} className={btnGhost}>淘汰</button>
                  </>
                )}
                <button type="button" onClick={() => handleDelete(skill.skill_id)} disabled={loading} className={btnDanger}>删除</button>
              </div>
            </div>
            {skill.description && <div className="mt-1.5 text-[12px] leading-4 text-neutral-400">{skill.description}</div>}
            {skill.system_prompt_hint && (
              <div className="mt-0.5 text-[11px] leading-4 text-neutral-600">
                hint: {skill.system_prompt_hint}{skill.system_prompt_truncated ? "…" : ""}
              </div>
            )}
            <div className="mt-1.5 flex flex-wrap items-baseline gap-x-4 gap-y-0.5 font-mono text-[11px] text-neutral-600">
              <span>trigger: {skill.trigger_pattern || "—"}</span>
              <span>uses: {skill.use_count}</span>
              <span>success: {Math.round(skill.success_rate * 100)}%</span>
              {skill.steps.length > 0 && (
                <span>tools: {skill.steps.map((s) => s.tool).join(" → ")}</span>
              )}
            </div>
          </div>
        ))}
      </div>
      <ConfirmDialog />
    </div>
  );
}
