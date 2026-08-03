import { useCallback, useEffect, useRef, useState } from "react";
import {
  addMcpServer,
  callMcpTool,
  connectMcpServer,
  listMcpServers,
  listMcpTools,
  removeMcpServer,
  type MCPServerView,
  type MCPToolView,
} from "../../api";
import { SectionTitle } from "./GeneralSettings";
import { useConfirm } from "../../hooks/useConfirm";

export default function McpServersSettings() {
  const [servers, setServers] = useState<MCPServerView[]>([]);
  const [tools, setTools] = useState<MCPToolView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const errTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { confirm, ConfirmDialog } = useConfirm();

  const showError = (msg: string) => {
    setError(msg);
    if (errTimer.current) clearTimeout(errTimer.current);
    errTimer.current = setTimeout(() => setError(null), 6000);
  };

  // 表单状态
  const [form, setForm] = useState({ name: "", transport: "stdio", command: "", args: "", url: "" });

  const refresh = useCallback(async () => {
    try {
      const [srvs, tls] = await Promise.all([listMcpServers(), listMcpTools()]);
      setServers(srvs);
      setTools(tls);
      setError(null);
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleAdd = async () => {
    if (!form.name.trim()) return;
    setLoading(true);
    try {
      await addMcpServer({
        name: form.name.trim(),
        transport: form.transport,
        command: form.command.trim(),
        args: form.args.split(/\s+/).filter(Boolean),
        url: form.url.trim(),
        enabled: true,
      });
      setForm({ name: "", transport: "stdio", command: "", args: "", url: "" });
      setShowForm(false);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (name: string) => {
    const ok = await confirm({ title: "删除 MCP 服务器", message: `确定删除「${name}」？删除后其工具将不可用。`, danger: true, confirmText: "删除" });
    if (!ok) return;
    setLoading(true);
    try {
      await removeMcpServer(name);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (name: string) => {
    setLoading(true);
    try {
      await connectMcpServer(name);
      await refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleTestTool = async (tool: MCPToolView) => {
    setTestResult(null);
    try {
      const res = await callMcpTool(tool.server, tool.name, {});
      setTestResult(JSON.stringify(res, null, 2));
    } catch (e: unknown) {
      setTestResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <SectionTitle title="MCP 服务器" description="动态接入任意 MCP Server，发现的工具自动注册到 Agent。" />
        <button
          type="button"
          onClick={() => setShowForm(!showForm)}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm text-neutral-300 transition hover:border-white/20 hover:text-neutral-100"
        >
          {showForm ? "取消" : "+ 添加服务器"}
        </button>
      </div>

      {error && <div className="rounded-lg bg-red-500/10 px-4 py-2 text-xs text-red-400">{error}</div>}

      {/* 添加表单 */}
      {showForm && (
        <div className="space-y-3 rounded-lg border border-neutral-700 bg-neutral-900/80 p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">名称 *</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="my-server"
                className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">传输协议</span>
              <select
                value={form.transport}
                onChange={(e) => setForm({ ...form, transport: e.target.value })}
                className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
              >
                <option value="stdio">stdio</option>
                <option value="sse">sse</option>
                <option value="streamable_http">streamable_http</option>
              </select>
            </label>
          </div>
          {form.transport === "stdio" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="space-y-1">
                <span className="text-xs text-neutral-400">启动命令</span>
                <input
                  value={form.command}
                  onChange={(e) => setForm({ ...form, command: e.target.value })}
                  placeholder="python / node / npx"
                  className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-neutral-400">参数（空格分隔）</span>
                <input
                  value={form.args}
                  onChange={(e) => setForm({ ...form, args: e.target.value })}
                  placeholder="-m mcp_server --port 3001"
                  className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
                />
              </label>
            </div>
          ) : (
            <label className="space-y-1">
              <span className="text-xs text-neutral-400">服务地址 URL</span>
              <input
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="http://localhost:3001/sse"
                className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
              />
            </label>
          )}
          <button
            type="button"
            onClick={handleAdd}
            disabled={loading || !form.name.trim()}
            className="rounded-lg bg-neutral-100 px-5 py-2 text-sm font-medium text-black transition hover:bg-white disabled:opacity-40"
          >
            {loading ? "连接中..." : "添加并连接"}
          </button>
        </div>
      )}

      {/* 服务器列表 */}
      <div className="grid gap-3">
        {servers.length === 0 && (
          <div className="rounded-lg border border-dashed border-neutral-700 p-6 text-center text-sm text-neutral-500">
            暂无 MCP 服务器。点击「添加服务器」接入任意 MCP Server。
          </div>
        )}
        {servers.map((srv) => (
          <div key={srv.name} className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className={`h-2.5 w-2.5 rounded-full ${srv.connected ? "bg-emerald-400" : "bg-neutral-600"}`} />
                <span className="text-sm font-medium text-white">{srv.name}</span>
                <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-[11px] text-neutral-400">{srv.transport}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-neutral-500">{srv.tools_count ?? 0} 工具</span>
                <button
                  type="button"
                  onClick={() => handleConnect(srv.name)}
                  disabled={loading}
                  className="rounded-lg bg-neutral-800 px-2.5 py-1 text-xs text-neutral-300 transition hover:bg-neutral-700"
                >
                  重连
                </button>
                <button
                  type="button"
                  onClick={() => handleRemove(srv.name)}
                  disabled={loading}
                  className="rounded-lg bg-red-500/10 px-2.5 py-1 text-xs text-red-400 transition hover:bg-red-500/20"
                >
                  删除
                </button>
              </div>
            </div>
            <div className="mt-2 text-xs text-neutral-500">
              {srv.transport === "stdio" ? `${srv.command} ${srv.args?.join(" ") ?? ""}` : srv.url || "—"}
            </div>
          </div>
        ))}
      </div>

      {/* 已发现工具 */}
      {tools.length > 0 && (
        <section className="space-y-3">
          <div className="text-sm font-medium text-neutral-300">已发现工具 ({tools.length})</div>
          <div className="grid gap-2">
            {tools.map((tool) => (
              <div key={`${tool.server}/${tool.name}`} className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900/60 px-4 py-3">
                <div>
                  <span className="text-sm text-white">{tool.name}</span>
                  <span className="ml-2 text-[11px] text-neutral-500">[{tool.server}]</span>
                  {tool.description && <div className="mt-0.5 text-xs text-neutral-500">{tool.description}</div>}
                </div>
                <button
                  type="button"
                  onClick={() => handleTestTool(tool)}
                  className="rounded-lg bg-neutral-800 px-2.5 py-1 text-xs text-neutral-300 transition hover:bg-neutral-700"
                >
                  测试
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 测试结果 */}
      {testResult && (
        <div className="rounded-lg border border-neutral-700 bg-neutral-900 p-4">
          <div className="mb-2 text-xs font-medium text-neutral-400">调用结果</div>
          <pre className="max-h-48 overflow-auto text-xs text-emerald-300">{testResult}</pre>
        </div>
      )}
      <ConfirmDialog />
    </div>
  );
}
