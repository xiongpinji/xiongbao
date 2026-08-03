import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { getSystemCapabilities, type SystemCapabilities } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function CommandsSettings() {
  const [caps, setCaps] = useState<SystemCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getSystemCapabilities()
      .then(setCaps)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const commands = caps?.commands ?? [];

  return (
    <div className="max-w-3xl space-y-6">
      <SectionTitle title="命令" description="工作区内置的 slash 命令。" />
      {error && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <span>{error}</span>
          <button
            type="button"
            onClick={load}
            className="shrink-0 rounded-md border border-red-500/30 px-3 py-1 text-xs font-medium text-red-300 transition hover:bg-red-500/10"
          >
            重试
          </button>
        </div>
      )}
      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-neutral-500">
          <Loader2 size={14} className="animate-spin" /> 正在加载命令...
        </div>
      ) : commands.length === 0 ? (
        <div className="rounded-lg border border-dashed border-white/[0.08] p-6 text-center text-sm text-neutral-500">
          暂无内置命令
        </div>
      ) : (
        <div className="space-y-2">
          {commands.map((cmd) => (
            <div key={cmd.name} className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 px-4 py-2.5">
              <span className="font-mono text-sm text-white">{cmd.name}</span>
              <span className="text-xs text-neutral-500">{cmd.description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
