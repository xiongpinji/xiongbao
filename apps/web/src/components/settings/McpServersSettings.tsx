import { useEffect, useState } from "react";
import { getSystemCapabilities, type SystemCapabilities } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function McpServersSettings() {
  const [caps, setCaps] = useState<SystemCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystemCapabilities()
      .then(setCaps)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const servers = caps?.mcp_servers ?? [];

  return (
    <div className="max-w-4xl space-y-6">
      <SectionTitle title="MCP 服务器" description="当前已配置的 MCP 网关与 stdio server。配置由 XAGENT_MCP_SERVERS 加载。" />
      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="grid gap-3">
        {servers.length === 0 && <div className="rounded-2xl border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">当前未启用任何 MCP server。可通过环境变量 `XAGENT_MCP_SERVERS` 注入 stdio / HTTP 配置。</div>}
        {servers.map((srv) => (
          <div key={srv.name} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-white">{srv.name}</div>
              <span className={`rounded-full px-2 py-0.5 text-[11px] ${srv.enabled ? "bg-emerald-500/10 text-emerald-300" : "bg-neutral-800 text-neutral-500"}`}>
                {srv.enabled ? "已启用" : "未启用"}
              </span>
            </div>
            <div className="mt-1 text-xs text-neutral-500">{srv.kind} · {srv.endpoint || "—"}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
