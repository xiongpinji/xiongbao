import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, Plus, Shield, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import { useConfirm } from "../../hooks/useConfirm";

interface WebhookView {
  webhook_id: string;
  url: string;
  events: string[];
  enabled: boolean;
  created_at: number;
}

export default function WebhookSettings() {
  const [hooks, setHooks] = useState<WebhookView[]>([]);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [scanning, setScanning] = useState(false);
  const errTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState("agent.completed");
  // 安全扫描
  const [scanText, setScanText] = useState("");
  const [scanResult, setScanResult] = useState<{ safe: boolean; risks: { type: string; detail: string }[]; masked_text: string } | null>(null);
  const { confirm, ConfirmDialog } = useConfirm();

  const showError = (msg: string) => {
    setError(msg);
    if (errTimer.current) clearTimeout(errTimer.current);
    errTimer.current = setTimeout(() => setError(""), 6000);
  };

  const refresh = useCallback(async () => {
    try {
      const resp = await api.get("/system/webhooks");
      setHooks(resp.data.webhooks);
      setError("");
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const addHook = async () => {
    if (!url.trim()) return;
    setAdding(true);
    try {
      await api.post("/system/webhooks", { url: url.trim(), events: events.split(",").map(e => e.trim()).filter(Boolean) });
      setUrl(""); setEvents("agent.completed");
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "注册失败");
    } finally {
      setAdding(false);
    }
  };

  const deleteHook = async (id: string) => {
    const ok = await confirm({ title: "删除 Webhook", message: "确定删除该 Webhook 订阅？", danger: true, confirmText: "删除" });
    if (!ok) return;
    try {
      await api.delete(`/system/webhooks/${id}`);
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const runScan = async () => {
    if (!scanText.trim()) return;
    setScanning(true);
    try {
      const resp = await api.post("/audit/content-scan", { text: scanText, direction: "input" });
      setScanResult(resp.data);
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "扫描失败");
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>
      )}

      {/* Webhook 管理 */}
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-lg font-medium text-white"><Bell size={18} className="text-neutral-400" /> Webhook 通知</h3>
        <div className="mb-4 flex gap-2">
          <input value={url} onChange={e => setUrl(e.target.value)} className="flex-1 rounded-lg border border-white/10 bg-black/30 px-4 py-2 text-sm text-white outline-none transition-colors focus:border-white/25" placeholder="回调 URL (https://...)" />
          <input value={events} onChange={e => setEvents(e.target.value)} className="w-48 rounded-lg border border-white/10 bg-black/30 px-4 py-2 text-sm text-white outline-none transition-colors focus:border-white/25" placeholder="事件(逗号分隔)" />
          <button onClick={addHook} disabled={adding || !url.trim()} className="flex items-center gap-1.5 rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-black transition hover:bg-white disabled:opacity-40">
            <Plus size={15} /> {adding ? "注册中…" : "注册"}
          </button>
        </div>
        <div className="space-y-2">
          {hooks.map(h => (
            <div key={h.webhook_id} className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3">
              <div>
                <span className="text-sm text-white">{h.url}</span>
                <span className="ml-3 text-xs text-neutral-500">{h.events.join(", ")}</span>
              </div>
              <button onClick={() => deleteHook(h.webhook_id)} className="text-neutral-500 transition hover:text-red-400"><Trash2 size={15} /></button>
            </div>
          ))}
          {hooks.length === 0 && <p className="text-sm text-neutral-500">暂无 Webhook</p>}
        </div>
      </section>

      {/* 内容安全扫描 */}
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-lg font-medium text-white"><Shield size={18} className="text-neutral-400" /> 内容安全扫描</h3>
        <div className="flex gap-2">
          <textarea value={scanText} onChange={e => setScanText(e.target.value)} rows={3} className="flex-1 rounded-lg border border-white/10 bg-black/30 px-4 py-2 text-sm text-white outline-none transition-colors focus:border-white/25" placeholder="输入文本进行注入检测 + PII 扫描..." />
          <button onClick={runScan} disabled={scanning || !scanText.trim()} className="self-start rounded-lg border border-white/10 px-4 py-2 text-sm text-neutral-300 transition hover:border-white/20 hover:text-neutral-100 disabled:opacity-40">{scanning ? "扫描中…" : "扫描"}</button>
        </div>
        {scanResult && (
          <div className={`mt-3 rounded-lg border px-4 py-3 text-sm ${scanResult.safe ? "border-green-500/30 bg-green-500/10 text-green-300" : "border-red-500/30 bg-red-500/10 text-red-300"}`}>
            <p className="font-medium">{scanResult.safe ? "安全" : "检测到风险"}</p>
            {scanResult.risks.map((r, i) => (
              <p key={i} className="mt-1 text-xs">[{r.type}] {r.detail}</p>
            ))}
            {scanResult.masked_text && (
              <p className="mt-2 text-xs text-neutral-400">脱敏: {scanResult.masked_text}</p>
            )}
          </div>
        )}
      </section>
      <ConfirmDialog />
    </div>
  );
}
