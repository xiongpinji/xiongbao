import type { RunTimelineEntry } from "../../api/runtime.ts";

function describeDetail(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
}

function formatTimestamp(ts: string): string {
  if (!ts) return "未记录时间";
  const date = new Date(ts);
  return Number.isNaN(date.getTime()) ? ts : date.toLocaleString("zh-CN", { hour12: false });
}

export default function RunTimelinePanel({ timeline }: { timeline: RunTimelineEntry[] }) {
  if (!timeline.length) {
    return <div className="rounded-2xl border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">暂无时间线事件。</div>;
  }

  return (
    <div className="space-y-3">
      {timeline.map((event, index) => (
        <article key={`${event.source}-${event.step_id}-${event.ts}-${index}`} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">{event.kind}</div>
              <div className="mt-1 text-xs text-neutral-500">{formatTimestamp(event.ts)}</div>
            </div>
            <div className="text-right text-xs text-neutral-500">
              <div>{event.source}</div>
              <div className="mt-1 font-mono text-[11px] text-neutral-600">{event.step_id}</div>
            </div>
          </div>
          <pre className="mt-3 overflow-auto rounded-2xl border border-neutral-800 bg-neutral-900 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
            {describeDetail(event.detail)}
          </pre>
        </article>
      ))}
    </div>
  );
}
