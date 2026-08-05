import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { getSystemCapabilities, type SystemCapabilities } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function PluginSettings() {
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

  return (
    <div className="max-w-4xl space-y-6">
      <SectionTitle title="插件管理" description="工作台当前已注册的工具与 MCP 发现的能力。" />
      {error && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <span>{error}</span>
          <button type="button" onClick={load} className="shrink-0 rounded-md border border-red-500/30 px-3 py-1 text-xs font-medium text-red-300 transition hover:bg-red-500/10">重试</button>
        </div>
      )}
      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-neutral-500">
          <Loader2 size={14} className="animate-spin" /> 正在加载插件...
        </div>
      ) : (
      <div className="grid gap-3 md:grid-cols-2">
        {(caps?.tools ?? []).map((tool) => (
          <div key={tool.name} className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-white">{tool.name}</div>
              <span className="font-mono text-xs text-neutral-500">{tool.kind}</span>
            </div>
            {tool.description && <div className="mt-1 text-xs text-neutral-400">{tool.description}</div>}
          </div>
        ))}
        {!caps?.tools?.length && <div className="rounded-lg border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">尚未注册工具。</div>}
      </div>
      )}
    </div>
  );
}
