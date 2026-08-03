import { ExternalLink } from "lucide-react";
import type { RuntimeArtifactRecord } from "../../api/runtime.ts";

function stringifyPreview(preview: Record<string, unknown> | undefined): string {
  if (!preview) return "";
  const parts = [preview.title, preview.prompt, preview.mode, preview.label]
    .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    .slice(0, 2);
  return parts.join(" · ");
}

function isOpenableArtifactUri(uri: string): boolean {
  const value = uri.trim();
  return value.length > 0 && !value.startsWith("placeholder://");
}

export default function RunArtifactsPanel({ artifacts }: { artifacts: RuntimeArtifactRecord[] }) {
  if (!artifacts.length) {
    return <div className="rounded-lg border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">暂无产物。</div>;
  }

  return (
    <div className="space-y-3">
      {artifacts.map((artifact) => {
        const preview = stringifyPreview(artifact.preview_summary);
        const canOpen = isOpenableArtifactUri(artifact.uri);
        return (
          <article key={artifact.artifact_id} className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-white">{artifact.name}</div>
                <div className="mt-1 text-xs text-neutral-500">{artifact.kind} · {artifact.content_type || "unknown"}</div>
              </div>
              {canOpen ? (
                <a
                  href={artifact.uri}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:border-neutral-500 hover:text-white"
                >
                  <ExternalLink size={12} />
                  打开
                </a>
              ) : (
                <span className="inline-flex items-center rounded-lg border border-dashed border-neutral-700 px-3 py-1.5 text-xs text-neutral-500">
                  {artifact.uri.trim().startsWith("placeholder://") ? "占位产物" : "暂无链接"}
                </span>
              )}
            </div>
            {preview && <div className="mt-3 text-xs leading-5 text-neutral-400">{preview}</div>}
            <div className="mt-3 grid gap-2 text-xs text-neutral-500 sm:grid-cols-2">
              <div>
                <span className="text-neutral-400">artifact</span>
                <div className="mt-1 font-mono text-[11px] text-neutral-500">{artifact.artifact_id}</div>
              </div>
              <div>
                <span className="text-neutral-400">task</span>
                <div className="mt-1 font-mono text-[11px] text-neutral-500">{artifact.task_id || "—"}</div>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
