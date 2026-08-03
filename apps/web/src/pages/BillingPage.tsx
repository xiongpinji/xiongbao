import { useCallback, useEffect, useState } from "react";
import { CreditCard, Gauge, Receipt, Zap } from "lucide-react";
import {
  getBillingSummary,
  getBillingRecords,
  setBillingPlan,
  type BillingSummary,
  type BillingRecord,
} from "../api/enterprise";
import { formatDateTime } from "../lib/time";
import { formatCost } from "../lib/format";

const PLAN_LABELS: Record<string, string> = {
  free: "免费版",
  pro: "专业版",
  enterprise: "企业版",
};

function UsageBar({ label, used, max }: { label: string; used: number; max: number }) {
  const pct = max > 0 ? Math.min((used / max) * 100, 100) : 0;
  const color = pct > 90 ? "bg-red-500" : pct > 70 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-neutral-400">
        <span>{label}</span>
        <span>
          {used.toLocaleString()} / {max.toLocaleString()}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function BillingPage() {
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [records, setRecords] = useState<BillingRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [s, r] = await Promise.all([getBillingSummary(), getBillingRecords()]);
      setSummary(s);
      setRecords(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handlePlanChange = async (plan: "free" | "pro" | "enterprise") => {
    try {
      const updated = await setBillingPlan(plan);
      setSummary(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "切换失败");
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-neutral-500">
        加载中...
      </div>
    );
  }

  return (
    <div className="xagent-scrollbar h-full overflow-auto bg-transparent px-4 py-6 text-neutral-100 md:px-8">
      <div className="mx-auto max-w-5xl space-y-8">
        {/* Header */}
        <header className="border-b border-white/[0.07] pb-5">
          <div className="text-xs font-medium tracking-wide text-neutral-500">
            Billing & Usage
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">计费与用量</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-500">
            查看当前订阅档位、配额使用情况和账单明细。
          </p>
        </header>

        {error && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => load()}
              className="shrink-0 rounded-md border border-red-500/30 px-3 py-1 text-xs font-medium text-red-300 transition hover:bg-red-500/10"
            >
              重试
            </button>
          </div>
        )}

        {summary && (
          <>
            {/* Plan + Usage */}
            <section className="grid gap-4 md:grid-cols-2">
              {/* Current Plan */}
              <div className="space-y-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
                <div className="flex items-center gap-2">
                  <CreditCard size={18} className="text-neutral-300" />
                  <span className="text-sm font-semibold text-white">当前订阅</span>
                </div>
                <div className="text-2xl font-bold text-white">
                  {PLAN_LABELS[summary.plan] ?? summary.plan}
                </div>
                <div className="flex gap-2">
                  {(["free", "pro", "enterprise"] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => handlePlanChange(p)}
                      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                        summary.plan === p
                          ? "bg-neutral-100 text-black"
                          : "bg-white/[0.06] text-neutral-400 hover:bg-white/[0.12]"
                      }`}
                    >
                      {PLAN_LABELS[p]}
                    </button>
                  ))}
                </div>
              </div>

              {/* Usage Bars */}
              <div className="space-y-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
                <div className="flex items-center gap-2">
                  <Gauge size={18} className="text-neutral-300" />
                  <span className="text-sm font-semibold text-white">配额使用</span>
                </div>
                <UsageBar
                  label="Agent 运行次数"
                  used={summary.usage.agent_runs}
                  max={summary.quota.max_agent_runs}
                />
                <UsageBar
                  label="媒体生成次数"
                  used={summary.usage.media_generations}
                  max={summary.quota.max_media_generations}
                />
                <UsageBar
                  label="Token 消耗"
                  used={summary.usage.tokens}
                  max={summary.quota.max_tokens}
                />
              </div>
            </section>

            {/* Stats */}
            <section className="grid gap-3 md:grid-cols-3">
              {[
                { icon: Zap, label: "Agent 运行", value: summary.usage.agent_runs.toLocaleString() },
                { icon: Gauge, label: "媒体生成", value: summary.usage.media_generations.toLocaleString() },
                { icon: Receipt, label: "账单记录", value: summary.records_count.toLocaleString() },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                    <Icon size={20} className="text-neutral-300" />
                    <div>
                      <div className="text-lg font-bold text-white">{item.value}</div>
                      <div className="text-xs text-neutral-500">{item.label}</div>
                    </div>
                  </div>
                );
              })}
            </section>

            {/* Records Table */}
            <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
              <h2 className="mb-4 text-sm font-semibold text-white">账单明细</h2>
              {records.length === 0 ? (
                <p className="text-sm text-neutral-500">暂无账单记录</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-neutral-500">
                        <th className="pb-2 pr-4">时间</th>
                        <th className="pb-2 pr-4">操作者</th>
                        <th className="pb-2 pr-4">动作</th>
                        <th className="pb-2 pr-4">费用</th>
                        <th className="pb-2">Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.slice(0, 50).map((r, i) => (
                        <tr key={i} className="border-b border-white/[0.04] text-neutral-300">
                          <td className="py-2 pr-4 whitespace-nowrap">
                            {formatDateTime(r.ts)}
                          </td>
                          <td className="py-2 pr-4">{r.actor}</td>
                          <td className="py-2 pr-4">
                            <span className="rounded bg-white/[0.06] px-1.5 py-0.5">{r.action}</span>
                          </td>
                          <td className="py-2 pr-4">{formatCost(r.cost)}</td>
                          <td className="py-2">{r.tokens.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
