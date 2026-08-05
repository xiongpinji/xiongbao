export interface CanvasTimelineEvent {
  ts: string;
  step_id: string;
  kind: string;
  detail: unknown;
}

export default function CanvasRunTimeline({ events }: { events: CanvasTimelineEvent[] }) {
  if (!events.length) {
    return <div className="rounded-lg border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">暂无运行日志。</div>;
  }

  return (
    <div className="space-y-2">
      {events.map((event, index) => (
        <div key={`${event.ts}-${index}`} className="rounded-lg border border-neutral-800 bg-neutral-950 p-3 text-sm">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium text-white">{event.kind}</span>
            <span className="font-mono text-xs text-neutral-600">{event.step_id}</span>
          </div>
          <div className="mt-1 text-xs text-neutral-500">{event.ts}</div>
          <div className="mt-2 line-clamp-3 text-xs leading-5 text-neutral-400">{String(event.detail ?? "")}</div>
        </div>
      ))}
    </div>
  );
}
