import { useCallback, useEffect, useState } from "react";
import { BookOpen, Plus, Search, Trash2 } from "lucide-react";
import { api } from "../../api/client";

interface DocView {
  doc_id: string;
  title: string;
  source: string;
  chunk_count: number;
  created_at: number;
  tags: string[];
}

interface SearchResult {
  text: string;
  score: number;
  title: string;
}

export default function KnowledgeSettings() {
  const [docs, setDocs] = useState<DocView[]>([]);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [tags, setTags] = useState("");
  // 检索
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);

  const refresh = useCallback(async () => {
    try {
      const resp = await api.get("/knowledge/documents");
      setDocs(resp.data.documents);
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const ingest = async () => {
    try {
      await api.post("/knowledge/ingest", {
        title,
        text,
        tags: tags.split(",").map(t => t.trim()).filter(Boolean),
      });
      setShowForm(false);
      setTitle(""); setText(""); setTags("");
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "上传失败");
    }
  };

  const deleteDoc = async (docId: string) => {
    try {
      await api.delete(`/knowledge/documents/${docId}`);
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const search = async () => {
    try {
      const resp = await api.post("/knowledge/search", { query, top_k: 5 });
      setResults(resp.data.results);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "检索失败");
    }
  };

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>
      )}

      {/* 语义检索 */}
      <section>
        <h3 className="mb-3 text-lg font-medium text-white">语义检索</h3>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && search()}
            className="flex-1 rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white outline-none focus:border-[#d6ad62]/50"
            placeholder="输入查询内容进行语义检索..."
          />
          <button onClick={search} className="flex items-center gap-1.5 rounded-xl bg-[#d6ad62]/15 px-4 py-2 text-sm text-[#d6ad62] transition hover:bg-[#d6ad62]/25">
            <Search size={15} /> 检索
          </button>
        </div>
        {results.length > 0 && (
          <div className="mt-3 space-y-2">
            {results.map((r, i) => (
              <div key={i} className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
                <div className="flex items-center justify-between text-xs text-neutral-500">
                  <span>{r.title}</span>
                  <span className="text-[#d6ad62]">score: {r.score.toFixed(3)}</span>
                </div>
                <p className="mt-1 text-sm text-neutral-300 line-clamp-3">{r.text}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 文档管理 */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">知识库文档</h3>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1.5 rounded-xl bg-[#d6ad62]/15 px-3 py-1.5 text-sm text-[#d6ad62] transition hover:bg-[#d6ad62]/25"
          >
            <Plus size={15} /> 上传文档
          </button>
        </div>

        {showForm && (
          <div className="mb-4 space-y-3 rounded-xl border border-white/[0.07] bg-white/[0.03] p-4">
            <input value={title} onChange={e => setTitle(e.target.value)} className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-[#d6ad62]/50" placeholder="文档标题" />
            <textarea value={text} onChange={e => setText(e.target.value)} rows={5} className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-[#d6ad62]/50" placeholder="文档内容（支持纯文本/Markdown）" />
            <div className="flex items-center gap-3">
              <input value={tags} onChange={e => setTags(e.target.value)} className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-[#d6ad62]/50" placeholder="标签（逗号分隔）" />
              <button onClick={ingest} className="rounded-lg bg-[#d6ad62] px-4 py-2 text-sm font-medium text-black transition hover:brightness-110">入库</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {docs.map(d => (
            <div key={d.doc_id} className="flex items-center justify-between rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
              <div className="flex items-center gap-3">
                <BookOpen size={16} className="text-[#d6ad62]" />
                <div>
                  <span className="text-sm font-medium text-white">{d.title}</span>
                  <span className="ml-2 text-xs text-neutral-500">{d.chunk_count} 块</span>
                  {d.tags.length > 0 && <span className="ml-2 text-xs text-neutral-600">{d.tags.join(", ")}</span>}
                </div>
              </div>
              <button onClick={() => deleteDoc(d.doc_id)} className="text-neutral-500 transition hover:text-red-400">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
          {docs.length === 0 && <p className="text-sm text-neutral-500">暂无文档，点击上方按钮上传</p>}
        </div>
      </section>
    </div>
  );
}
