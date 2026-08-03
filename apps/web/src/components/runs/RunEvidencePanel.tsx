import type { RuntimeEvidenceRecord } from "../../api/runtime.ts";

function summarizePayload(payload: unknown): string {
  if (payload == null) return "无 payload";
  if (typeof payload === "string") return payload;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

export default function RunEvidencePanel({ evidence }: { evidence: RuntimeEvidenceRecord[] }) {
  if (!evidence.length) {
    return <div className="rounded-lg border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">暂无 evidence。</div>;
  }

  return (
    <div className="space-y-3">
      {evidence.map((item) => (
        <article key={item.evidence_id} className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">{item.kind}</div>
              <div className="mt-1 text-xs text-neutral-500">evidence {item.evidence_id}</div>
            </div>
            <div className="text-right text-xs text-neutral-500">
              <div>task {item.task_id || "—"}</div>
              <div>artifact {item.artifact_id || "—"}</div>
            </div>
          </div>
          <pre className="mt-3 overflow-auto rounded-lg border border-neutral-800 bg-neutral-900 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
            {summarizePayload(item.payload)}
          </pre>
        </article>
      ))}
    </div>
  );
}
