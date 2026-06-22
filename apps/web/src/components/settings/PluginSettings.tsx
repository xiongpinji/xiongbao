import { useEffect, useState } from "react";
import { getSystemCapabilities, type SystemCapabilities } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function PluginSettings() {
  const [caps, setCaps] = useState<SystemCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystemCapabilities()
      .then(setCaps)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="max-w-4xl space-y-6">
      <SectionTitle title="插件管理" description="工作台当前已注册的工具与 MCP 发现的能力。" />
      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="grid gap-3 md:grid-cols-2">
        {(caps?.tools ?? []).map((tool) => (
          <div key={tool.name} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-white">{tool.name}</div>
              <span className="font-mono text-xs text-neutral-500">{tool.kind}</span>
            </div>
            {tool.description && <div className="mt-1 text-xs text-neutral-400">{tool.description}</div>}
          </div>
        ))}
        {!caps?.tools?.length && <div className="rounded-2xl border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">尚未注册工具。</div>}
      </div>
    </div>
  );
}
