import type { DramaArtifact } from "./canvasTypes";

export default function ArtifactPreview({ artifacts }: { artifacts: DramaArtifact[] }) {
  if (!artifacts.length) {
    return (
      <div className="rounded-lg border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">
        当前节点暂无产物。
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {artifacts.map((artifact) => (
        <div key={artifact.id} className="rounded-lg border border-neutral-800 bg-neutral-950 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">{artifact.title}</div>
              <div className="mt-1 text-xs text-neutral-500">{artifact.kind}{artifact.status ? ` · ${artifact.status}` : ""}</div>
            </div>
            {artifact.url && (
              <a href={artifact.url} target="_blank" rel="noreferrer" className="text-xs text-blue-300 hover:underline">
                打开
              </a>
            )}
          </div>
          {artifact.kind === "text" && typeof artifact.content === "string" && (
            <div className="mt-2 text-xs leading-5 text-neutral-400">{artifact.content}</div>
          )}
          {artifact.taskId && <div className="mt-2 font-mono text-[11px] text-neutral-600">task {artifact.taskId}</div>}
        </div>
      ))}
    </div>
  );
}
