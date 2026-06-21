import { useState } from "react";
import { writeMemory, searchMemory } from "../api";

export default function MemoryPage() {
  const [id, setId] = useState("");
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ id: string; text: string; score: number }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  async function write() {
    if (!id.trim() || !text.trim()) return;
    await writeMemory([{ id, text }]);
    setMsg(`已写入 ${id}`);
    setId("");
    setText("");
  }

  async function search() {
    if (!query.trim()) return;
    const r = await searchMemory(query);
    setHits(r);
  }

  return (
    <div className="p-6 max-w-3xl space-y-6">
      <h1 className="text-xl font-semibold">知识库（记忆）</h1>
      <div className="bg-white border rounded-md p-4 space-y-2">
        <div className="text-sm font-medium">写入</div>
        <input
          className="w-full border rounded px-2 py-1 text-sm"
          placeholder="id"
          value={id}
          onChange={(e) => setId(e.target.value)}
        />
        <textarea
          className="w-full border rounded px-2 py-1 text-sm"
          rows={2}
          placeholder="文本"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          className="px-3 py-1 bg-brand-600 text-white rounded text-sm"
          onClick={write}
        >
          写入
        </button>
        {msg && <div className="text-xs text-green-600">{msg}</div>}
      </div>

      <div className="bg-white border rounded-md p-4 space-y-2">
        <div className="text-sm font-medium">语义检索</div>
        <input
          className="w-full border rounded px-2 py-1 text-sm"
          placeholder="query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <button
          className="px-3 py-1 bg-brand-600 text-white rounded text-sm"
          onClick={search}
        >
          检索
        </button>
        <div className="space-y-1">
          {hits.map((h) => (
            <div key={h.id} className="text-sm border-t pt-1">
              <span className="text-xs text-slate-500 mr-2">{h.score.toFixed(3)}</span>
              {h.text}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
