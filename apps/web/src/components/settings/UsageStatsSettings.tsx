import { useEffect, useState } from "react";
import { listWorkflows, listProductions, listTimelines } from "../../api";
import { StatLine, SectionHeader } from "./ui";

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
    <div className="max-w-3xl">
      <SectionHeader title="usage" desc="查看工作流、短剧产物与剪辑时间线的真实数量。" />
      {error && <div className="text-xs text-red-400">{error}</div>}
      <StatLine items={items.map((it) => ({ label: it.label, value: it.value }))} />
    </div>
  );
}
