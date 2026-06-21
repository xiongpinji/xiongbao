import { useState } from "react";
import { runWorkflow, type WorkflowView } from "../api";

export default function WorkflowsPage() {
  const [name, setName] = useState("demo");
  const [stepsText, setStepsText] = useState(
    JSON.stringify([{ id: "s1", name: "打招呼", goal: "你好" }], null, 2)
  );
  const [view, setView] = useState<WorkflowView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const steps = JSON.parse(stepsText);
      setView(await runWorkflow({ name, steps }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-xl font-semibold mb-4">工作流</h1>
      <div className="bg-white border rounded-md p-4 space-y-3">
        <input
          className="w-full border rounded px-2 py-1 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="工作流名"
        />
        <textarea
          className="w-full border rounded px-2 py-1 text-xs font-mono"
          rows={6}
          value={stepsText}
          onChange={(e) => setStepsText(e.target.value)}
        />
        <button
          className="px-4 py-2 bg-brand-600 text-white rounded text-sm disabled:opacity-50"
          onClick={run}
          disabled={loading}
        >
          {loading ? "执行中..." : "创建并执行"}
        </button>
      </div>

      {error && <div className="mt-4 text-sm text-red-600">{error}</div>}

      {view && (
        <div className="mt-6 space-y-4">
          <div className="bg-white border rounded-md p-4">
            <div className="text-sm font-medium">
              状态：<span className="text-brand-700">{view.status}</span>
            </div>
            <div className="mt-3 space-y-2">
              {view.steps.map((s) => (
                <div key={s.id} className="text-sm flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-slate-400" />
                  <span>{s.name}</span>
                  <span className="text-xs text-slate-500">({s.status})</span>
                  {s.has_approval && (
                    <span className="text-xs bg-amber-100 text-amber-700 px-1.5 rounded">审批</span>
                  )}
                  {s.has_compensation && (
                    <span className="text-xs bg-blue-100 text-blue-700 px-1.5 rounded">可补偿</span>
                  )}
                </div>
              ))}
            </div>
          </div>
          <details className="bg-white border rounded-md p-4">
            <summary className="text-sm cursor-pointer">Timeline（{view.timeline.length}）</summary>
            <ol className="mt-2 text-xs space-y-1">
              {view.timeline.map((e, i) => (
                <li key={i}>
                  {e.ts.slice(11, 19)} · {e.step_id} · {e.kind}
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </div>
  );
}
