import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, Plus, Search, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import { useConfirm } from "../../hooks/useConfirm";

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
  const [ingesting, setIngesting] = useState(false);
  const [searching, setSearching] = useState(false);
  const errTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [tags, setTags] = useState("");
  // 检索
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const { confirm, ConfirmDialog } = useConfirm();

  const showError = (msg: string) => {
    setError(msg);
    if (errTimer.current) clearTimeout(errTimer.current);
    errTimer.current = setTimeout(() => setError(""), 6000);
  };

  const refresh = useCallback(async () => {
    try {
      const resp = await api.get("/knowledge/documents");
      setDocs(resp.data.documents);
      setError("");
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const ingest = async () => {
    if (!title.trim() || !text.trim()) return;
    setIngesting(true);
    try {
      await api.post("/knowledge/ingest", {
        title: title.trim(),
        text,
        tags: tags.split(",").map(t => t.trim()).filter(Boolean),
      });
      setShowForm(false);
      setTitle(""); setText(""); setTags("");
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setIngesting(false);
    }
  };

  const deleteDoc = async (docId: string) => {
    const ok = await confirm({ title: "删除文档", message: "确定从知识库中删除该文档及其切片？", danger: true, confirmText: "删除" });
    if (!ok) return;
    try {
      await api.delete(`/knowledge/documents/${docId}`);
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const resp = await api.post("/knowledge/search", { query: query.trim(), top_k: 5 });
      setResults(resp.data.results);
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "检索失败");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>
      )}

      {/* 语义检索 */}
      <section>
        <h3 className="mb-3 text-lg font-medium text-white">语义检索</h3>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.nativeEvent.isComposing && search()}
            className="flex-1 rounded-lg border border-white/10 bg-black/30 px-4 py-2 text-sm text-white outline-none transition-colors focus:border-white/25"
            placeholder="输入查询内容进行语义检索..."
          />
          <button onClick={search} disabled={searching || !query.trim()} className="flex items-center gap-1.5 rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-black transition hover:bg-white disabled:opacity-40">
            <Search size={15} /> {searching ? "检索中…" : "检索"}
          </button>
        </div>
        {results.length > 0 && (
          <div className="mt-3 space-y-2">
            {results.map((r, i) => (
              <div key={i} className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3">
                <div className="flex items-center justify-between text-xs text-neutral-500">
                  <span>{r.title}</span>
                  <span className="text-neutral-400">score: {r.score.toFixed(3)}</span>
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
            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-neutral-300 transition hover:border-white/20 hover:text-neutral-100"
          >
            <Plus size={15} /> 上传文档
          </button>
        </div>

        {showForm && (
          <div className="mb-4 space-y-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
            <input value={title} onChange={e => setTitle(e.target.value)} className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-white/25" placeholder="文档标题" />
            <textarea value={text} onChange={e => setText(e.target.value)} rows={5} className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-white/25" placeholder="文档内容（支持纯文本/Markdown）" />
            <div className="flex items-center gap-3">
              <input value={tags} onChange={e => setTags(e.target.value)} className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-white/25" placeholder="标签（逗号分隔）" />
              <button onClick={ingest} disabled={ingesting || !title.trim() || !text.trim()} className="rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-black transition hover:bg-white disabled:opacity-40">{ingesting ? "入库中…" : "入库"}</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {docs.map(d => (
            <div key={d.doc_id} className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3">
              <div className="flex items-center gap-3">
                <BookOpen size={16} className="text-neutral-500" />
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
      <ConfirmDialog />
    </div>
  );
}
