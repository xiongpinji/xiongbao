import type { ReactNode } from "react";

/**
 * ZCode/Codex 风格设置原语：扁平行式布局。
 * 原则：零卡片容器——分组用 hairline 分隔线，标签在左、控件在右，
 * 数值与状态用等宽字体，操作按钮 ghost 化（透明底 + 悬浮微亮）。
 */

/** 分区头：mono 大写小标题 + 描述 + 右侧动作区，下缘 hairline */
export function SectionHeader({
  title,
  desc,
  actions,
}: {
  title: string;
  desc?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-white/[0.07] pb-3">
      <div>
        <h2 className="font-mono text-[13px] font-semibold uppercase tracking-wider text-neutral-200">
          {title}
        </h2>
        {desc && <p className="mt-1 text-[12px] leading-4 text-neutral-500">{desc}</p>}
      </div>
      {actions && <div className="flex items-center gap-1.5">{actions}</div>}
    </div>
  );
}

/** 子分组标签：mono 小写 + 弱化 */
export function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mt-6 mb-1 font-mono text-[11px] uppercase tracking-widest text-neutral-600">
      {children}
    </div>
  );
}

/** 设置行：左侧 label + hint，右侧控件；行间 hairline */
export function Row({
  label,
  hint,
  children,
  stacked,
}: {
  label: ReactNode;
  hint?: ReactNode;
  children?: ReactNode;
  stacked?: boolean;
}) {
  if (stacked) {
    return (
      <div className="border-b border-white/[0.05] py-3">
        <div className="text-[13px] text-neutral-300">{label}</div>
        {hint && <div className="mt-0.5 text-[12px] leading-4 text-neutral-600">{hint}</div>}
        {children && <div className="mt-2.5">{children}</div>}
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.05] py-3">
      <div className="min-w-0">
        <div className="text-[13px] text-neutral-300">{label}</div>
        {hint && <div className="mt-0.5 text-[12px] leading-4 text-neutral-600">{hint}</div>}
      </div>
      {children && <div className="flex shrink-0 items-center gap-2">{children}</div>}
    </div>
  );
}

/** 内联统计行：mono 数值 + 弱标签，替代统计卡片 */
export function StatLine({
  items,
}: {
  items: { label: string; value: ReactNode; tone?: "ok" | "warn" | "muted" }[];
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 border-b border-white/[0.05] py-2.5 font-mono text-[12px]">
      {items.map((it) => (
        <span key={it.label}>
          <span
            className={
              it.tone === "ok"
                ? "text-emerald-400"
                : it.tone === "warn"
                  ? "text-amber-400"
                  : "text-neutral-200"
            }
          >
            {it.value}
          </span>
          <span className="ml-1.5 text-neutral-600">{it.label}</span>
        </span>
      ))}
    </div>
  );
}

/* ── 扁平按钮：透明底 + 悬浮微亮，替代彩色填充按钮 ── */

export const btnPrimary =
  "rounded-md bg-white/[0.08] px-3 py-1.5 text-[12px] font-medium text-neutral-100 transition hover:bg-white/[0.14] disabled:opacity-40";
export const btnGhost =
  "rounded-md px-3 py-1.5 text-[12px] text-neutral-400 transition hover:bg-white/[0.05] hover:text-neutral-200 disabled:opacity-40";
export const btnOk =
  "rounded-md px-3 py-1.5 text-[12px] text-emerald-400/90 transition hover:bg-emerald-500/10 disabled:opacity-40";
export const btnWarn =
  "rounded-md px-3 py-1.5 text-[12px] text-amber-400/90 transition hover:bg-amber-500/10 disabled:opacity-40";
export const btnDanger =
  "rounded-md px-3 py-1.5 text-[12px] text-red-400/90 transition hover:bg-red-500/10 disabled:opacity-40";

/* ── 扁平输入：细边框 + mono 值 ── */

export const inputCls =
  "w-full rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] font-mono text-neutral-100 outline-none transition focus:border-white/[0.2]";
export const textareaCls =
  "w-full rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]";
