import { useState } from "react";
import { discoverOpenSource, type ScoredCandidateDTO } from "../api";

export default function OpenSourcePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ScoredCandidateDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResults(await discoverOpenSource(query));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-xl font-semibold mb-4">开源候选发现</h1>
      <div className="flex gap-2 mb-4">
        <input
          className="flex-1 border rounded px-3 py-2 text-sm"
          placeholder="查询关键词，例如：vector database"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <button
          className="px-4 py-2 bg-brand-600 text-white rounded text-sm disabled:opacity-50"
          onClick={search}
          disabled={loading || !query.trim()}
        >
          {loading ? "搜索中..." : "发现"}
        </button>
      </div>

      {error && <div className="text-sm text-red-600 mb-3">{error}</div>}

      <div className="space-y-2">
        {results.map((r) => (
          <div key={r.name + r.source} className="bg-white border rounded-md p-3">
            <div className="flex items-center justify-between">
              <a
                href={r.url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-brand-700 hover:underline"
              >
                {r.name}
              </a>
              <span className="text-sm font-mono">{r.score.toFixed(3)}</span>
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {r.source} · ★{r.stars} · {r.license || "未知许可"} ·{" "}
              {r.license_ok ? (
                <span className="text-green-600">许可可用</span>
              ) : (
                <span className="text-red-600">许可风险</span>
              )}
            </div>
            {r.notes && <div className="text-xs text-amber-600 mt-1">{r.notes}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
