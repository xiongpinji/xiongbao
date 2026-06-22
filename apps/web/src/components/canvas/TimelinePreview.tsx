import type { EditorTimeline } from "../../api";

export default function TimelinePreview({ timeline }: { timeline?: EditorTimeline | null }) {
  if (!timeline) {
    return (
      <div className="rounded-2xl border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">
        剪辑节点尚未创建时间线。
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-white">{timeline.name}</div>
          <div className="mt-1 text-xs text-neutral-500">{timeline.width}×{timeline.height} · {timeline.fps}fps</div>
        </div>
        <div className="font-mono text-xs text-neutral-500">{timeline.total_duration.toFixed(1)}s</div>
      </div>
      <div className="mt-4 space-y-2">
        {timeline.clips.map((clip) => (
          <div key={clip.id} className="rounded-xl bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
            {clip.track_type} · {clip.duration.toFixed(1)}s · {clip.text || clip.source_url}
          </div>
        ))}
      </div>
    </div>
  );
}
