import { useEffect, useState } from "react";
import { listWorkflows, listProductions, listTimelines } from "../../api";
import { SectionTitle } from "./GeneralSettings";

interface Stats {
  workflows: number;
  productions: number;
  timelines: number;
}

export default function UsageStatsSettings() {
  const [stats, setStats] = useState<Stats>({ workflows: 0, productions: 0, timelines: 0 });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      listWorkflows().catch(() => []),
      listProductions().catch(() => []),
      listTimelines().catch(() => []),
    ])
      .then(([workflows, productions, timelines]) => {
        setStats({
          workflows: workflows?.length ?? 0,
          productions: productions?.length ?? 0,
          timelines: timelines?.length ?? 0,
        });
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const items = [
    { label: "工作流运行", value: stats.workflows },
    { label: "短剧产物", value: stats.productions },
    { label: "剪辑时间线", value: stats.timelines },
  ];

  return (
    <div className="max-w-3xl space-y-6">
      <SectionTitle title="使用统计" description="查看工作流、短剧产物与剪辑时间线的真实数量。" />
      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {items.map((item) => (
          <div key={item.label} className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
            <div className="text-xs text-neutral-500">{item.label}</div>
            <div className="mt-2 font-mono text-2xl text-white">{item.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
