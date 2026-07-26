import { useCallback, useEffect, useState } from "react";
import { Download, ShieldCheck, ShieldAlert, RefreshCw } from "lucide-react";
import {
  getAuditEvents,
  verifyAuditChain,
  exportAuditJson,
  type AuditListResponse,
  type AuditVerifyResponse,
} from "../api/enterprise";

export default function AuditPage() {
  const [data, setData] = useState<AuditListResponse | null>(null);
  const [verify, setVerify] = useState<AuditVerifyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [events, verification] = await Promise.all([getAuditEvents(), verifyAuditChain()]);
      setData(events);
      setVerify(verification);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const json = await exportAuditJson();
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "导出失败");
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-neutral-500">
        加载中...
      </div>
    );
  }

  const integrityValid = verify?.valid ?? data?.integrity.valid ?? false;

  return (
    <div className="xagent-scrollbar h-full overflow-auto bg-transparent px-4 py-6 text-neutral-100 md:px-8">
      <div className="mx-auto max-w-5xl space-y-8">
        {/* Header */}
        <header className="border-b border-white/[0.07] pb-5">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">
            Audit Trail
          </div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">审计日志</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-500">
            查看系统操作审计链，校验完整性，导出合规报告。
          </p>
        </header>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Integrity Status */}
        <section className="grid gap-4 md:grid-cols-3">
          <div
            className={`xagent-surface-subtle flex items-center gap-3 p-4 ${
              integrityValid ? "border-emerald-500/20" : "border-red-500/20"
            }`}
          >
            {integrityValid ? (
              <ShieldCheck size={24} className="text-emerald-400" />
            ) : (
              <ShieldAlert size={24} className="text-red-400" />
            )}
            <div>
              <div className="text-sm font-semibold text-white">
                {integrityValid ? "审计链完整" : "审计链异常"}
              </div>
              <div className="text-xs text-neutral-500">
                {integrityValid
                  ? "所有事件哈希校验通过"
                  : `首个断裂序号: ${verify?.first_broken_seq ?? "unknown"}`}
              </div>
            </div>
          </div>

          <div className="xagent-surface-subtle flex items-center gap-3 p-4">
            <RefreshCw size={20} className="text-[#d6ad62]" />
            <div>
              <div className="text-lg font-bold text-white">{data?.events.length ?? 0}</div>
              <div className="text-xs text-neutral-500">审计事件总数</div>
            </div>
          </div>

          <div className="xagent-surface-subtle flex items-center justify-center p-4">
            <button
              onClick={handleExport}
              disabled={exporting}
              className="gold-button flex items-center gap-2 text-sm"
            >
              <Download size={16} />
              {exporting ? "导出中..." : "导出审计 JSON"}
            </button>
          </div>
        </section>

        {/* Events Table */}
        <section className="xagent-surface-subtle p-5">
          <h2 className="mb-4 text-sm font-semibold text-white">审计事件</h2>
          {!data || data.events.length === 0 ? (
            <p className="text-sm text-neutral-500">暂无审计事件</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-white/[0.07] text-neutral-500">
                    <th className="pb-2 pr-3">Seq</th>
                    <th className="pb-2 pr-3">时间</th>
                    <th className="pb-2 pr-3">操作者</th>
                    <th className="pb-2 pr-3">动作</th>
                    <th className="pb-2 pr-3">详情</th>
                    <th className="pb-2">Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {data.events.slice(0, 100).map((evt) => (
                    <tr key={evt.seq} className="border-b border-white/[0.04] text-neutral-300">
                      <td className="py-2 pr-3 text-neutral-500">{evt.seq}</td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {new Date(evt.ts).toLocaleString("zh-CN")}
                      </td>
                      <td className="py-2 pr-3">{evt.actor}</td>
                      <td className="py-2 pr-3">
                        <span className="rounded bg-white/[0.06] px-1.5 py-0.5">{evt.action}</span>
                      </td>
                      <td className="max-w-[200px] truncate py-2 pr-3 text-neutral-500">
                        {JSON.stringify(evt.detail)}
                      </td>
                      <td className="py-2 font-mono text-[10px] text-neutral-600">
                        {evt.hash?.slice(0, 12)}...
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
