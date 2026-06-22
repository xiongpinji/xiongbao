import { useState } from "react";
import { discoverOpenSource, searchMemory, writeMemory, type ScoredCandidateDTO } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export type IndexTab = "knowledge" | "open-source";

export default function IndexSettings({ initialTab = "knowledge" }: { initialTab?: IndexTab }) {
  const [tab, setTab] = useState<IndexTab>(initialTab);

  return (
    <div className="max-w-5xl space-y-6">
      <SectionTitle title="索引库" description="统一管理知识库、记忆检索和开源候选发现。" />
      <div className="flex gap-2 rounded-2xl border border-neutral-800 bg-neutral-900 p-1">
        <TabButton active={tab === "knowledge"} onClick={() => setTab("knowledge")}>知识库</TabButton>
        <TabButton active={tab === "open-source"} onClick={() => setTab("open-source")}>开源发现</TabButton>
      </div>
      {tab === "knowledge" ? <KnowledgePanel /> : <OpenSourcePanel />}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-xl px-4 py-2 text-sm transition-colors ${
        active ? "bg-neutral-700 text-white" : "text-neutral-400 hover:bg-neutral-800 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}

function KnowledgePanel() {
  const [id, setId] = useState("");
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ id: string; text: string; score: number }[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function write() {
    if (!id.trim() || !text.trim()) return;
    setError(null);
    try {
      await writeMemory([{ id, text }]);
      setMessage(`已写入 ${id}`);
      setId("");
      setText("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function search() {
    if (!query.trim()) return;
    setError(null);
    try {
      setHits(await searchMemory(query));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-3xl border border-neutral-800 bg-neutral-900 p-5">
        <div className="mb-4 text-sm font-medium text-white">写入知识</div>
        <div className="space-y-3">
          <label className="block space-y-2">
            <span className="text-xs text-neutral-500">ID</span>
            <input className="field" value={id} onChange={(e) => setId(e.target.value)} placeholder="memory-id" />
          </label>
          <label className="block space-y-2">
            <span className="text-xs text-neutral-500">文本</span>
            <textarea className="field min-h-24" value={text} onChange={(e) => setText(e.target.value)} placeholder="写入需要检索的项目知识" />
          </label>
          <button className="primary-button" onClick={write} disabled={!id.trim() || !text.trim()}>写入</button>
          {message && <div className="text-xs text-emerald-400">{message}</div>}
          {error && <div className="text-xs text-red-400">{error}</div>}
        </div>
      </div>
      <div className="rounded-3xl border border-neutral-800 bg-neutral-900 p-5">
        <div className="mb-4 text-sm font-medium text-white">语义检索</div>
        <div className="flex gap-2">
          <input className="field" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder="输入检索问题" />
          <button className="primary-button" onClick={search} disabled={!query.trim()}>检索</button>
        </div>
        <div className="mt-4 space-y-2">
          {hits.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">暂无检索结果。</div>
          ) : (
            hits.map((hit) => (
              <div key={hit.id} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-3 text-sm text-neutral-300">
                <div className="mb-1 font-mono text-xs text-neutral-500">{hit.id} · {hit.score.toFixed(3)}</div>
                {hit.text}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function OpenSourcePanel() {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(10);
  const [results, setResults] = useState<ScoredCandidateDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResults(await discoverOpenSource(query, limit));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-3xl border border-neutral-800 bg-neutral-900 p-5">
      <div className="mb-4 text-sm font-medium text-white">开源候选发现</div>
      <div className="grid gap-3 md:grid-cols-[1fr_120px_auto]">
        <input className="field" placeholder="查询关键词，例如 vector database" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
        <input className="field" type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value) || 10)} />
        <button className="primary-button" onClick={search} disabled={loading || !query.trim()}>{loading ? "搜索中" : "发现"}</button>
      </div>
      {error && <div className="mt-3 text-xs text-red-400">{error}</div>}
      <div className="mt-4 space-y-2">
        {results.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">暂无候选结果。</div>
        ) : (
          results.map((result) => (
            <div key={result.name + result.source} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-4">
              <div className="flex items-center justify-between gap-3">
                <a href={result.url} target="_blank" rel="noreferrer" className="font-medium text-white hover:underline">{result.name}</a>
                <span className="font-mono text-sm text-neutral-400">{result.score.toFixed(3)}</span>
              </div>
              <div className="mt-2 text-xs text-neutral-500">
                {result.source} · stars {result.stars} · {result.license || "未知许可"} · {result.license_ok ? "许可可用" : "许可风险"}
              </div>
              {result.notes && <div className="mt-2 text-xs text-amber-400">{result.notes}</div>}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
