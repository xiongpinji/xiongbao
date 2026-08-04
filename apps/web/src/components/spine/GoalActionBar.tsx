import type { GoalBoardSnapshot } from "../../api/spine";

export interface AdvanceInput {
  enabled: boolean;
  auto_execute?: boolean;
}

export interface ReleaseInput {
  branch_name: string;
  commit_sha: string;
  pr_number?: string;
}

/**
 * P4 治理视图操作条：自动推进开关 + release 收口表单。
 * 无 hooks（展示型组件）：折叠用原生 <details>，表单非受控，
 * 变更全部由父级（GoalBoardPage）的 mutation 处理并通过 props 回传。
 */
export default function GoalActionBar({
  snapshot,
  busy,
  message,
  onToggleAdvance,
  onCreateRelease,
}: {
  snapshot: GoalBoardSnapshot;
  busy: boolean;
  message: string;
  onToggleAdvance: (input: AdvanceInput) => void;
  onCreateRelease: (input: ReleaseInput) => void;
}) {
  const goalId = snapshot.goal.goal_id ?? "";
  const autoAdvance = snapshot.goal.auto_advance ?? false;
  const autoExecute = snapshot.goal.auto_execute ?? false;

  return (
    <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium text-neutral-600">治理操作</span>
        <button
          type="button"
          disabled={busy || !goalId}
          onClick={() => onToggleAdvance({ enabled: !autoAdvance, auto_execute: autoExecute })}
          className="rounded-md border border-white/[0.08] px-3 py-1.5 text-[12px] text-neutral-300 transition-colors hover:border-white/[0.16] disabled:opacity-50"
        >
          {autoAdvance ? "关闭自动推进" : "开启自动推进"}
        </button>
        <button
          type="button"
          disabled={busy || !goalId || !autoAdvance}
          title={autoAdvance ? "" : "需先开启自动推进"}
          onClick={() => onToggleAdvance({ enabled: true, auto_execute: !autoExecute })}
          className="rounded-md border border-white/[0.08] px-3 py-1.5 text-[12px] text-neutral-300 transition-colors hover:border-white/[0.16] disabled:opacity-50"
        >
          {autoExecute ? "关闭自动执行" : "开启自动执行（消耗 LLM）"}
        </button>
        <span className="text-[11px] text-neutral-600">
          当前：自动推进 {autoAdvance ? "开" : "关"} · 自动执行 {autoExecute ? "开" : "关"}
        </span>
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] text-emerald-300">发起 Release 收口</summary>
        <form
          className="mt-2 grid gap-2 rounded-md border border-white/[0.06] p-3 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            onCreateRelease({
              branch_name: String(data.get("branch") ?? "").trim(),
              commit_sha: String(data.get("commit_sha") ?? "").trim(),
              pr_number: String(data.get("pr_number") ?? "").trim(),
            });
          }}
        >
          <input
            name="branch"
            required
            placeholder="分支名（如 candidate/x）"
            className="rounded-md border border-white/[0.08] bg-transparent px-2 py-1.5 text-[12px] text-neutral-200 placeholder:text-neutral-600"
          />
          <input
            name="commit_sha"
            required
            minLength={7}
            placeholder="commit sha（≥7 位）"
            className="rounded-md border border-white/[0.08] bg-transparent px-2 py-1.5 text-[12px] text-neutral-200 placeholder:text-neutral-600"
          />
          <input
            name="pr_number"
            placeholder="PR 号（可选）"
            className="rounded-md border border-white/[0.08] bg-transparent px-2 py-1.5 text-[12px] text-neutral-200 placeholder:text-neutral-600"
          />
          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-emerald-500/20 px-3 py-1.5 text-[12px] text-emerald-200 transition-colors hover:bg-emerald-500/30 disabled:opacity-50"
            >
              确认收口（release_ready → delivered）
            </button>
          </div>
        </form>
      </details>

      {message ? <div className="mt-2 text-[12px] text-neutral-400">{message}</div> : null}
    </section>
  );
}
