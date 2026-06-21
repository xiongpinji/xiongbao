import { useState } from "react";
import { runAgent, type AgentRun } from "../api";
import { getToken } from "../api/client";

export default function ChatPage() {
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!goal.trim()) return;
    setLoading(true);
    setError(null);
    setStreamText("");
    setRun(null);

    // 优先走 SSE 流式，失败回退普通 run
    try {
      await runSSE();
    } catch {
      try {
        setRun(await runAgent({ goal }));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  async function runSSE() {
    const token = getToken();
    const resp = await fetch("/api/v1/stream/agents/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ goal }),
    });
    if (!resp.ok || !resp.body) throw new Error(`SSE ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const evt of events) {
        const line = evt.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const data = JSON.parse(line.slice(5).trim());
        if (data.final_answer) setStreamText(data.final_answer);
        else if (data.error) setError(data.error);
      }
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">对话</h1>
      <textarea
        className="w-full border rounded-md p-3 text-sm"
        rows={3}
        placeholder="输入任务目标，例如：用一句话介绍 X-Agent"
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
      />
      <button
        className="mt-3 px-4 py-2 bg-brand-600 text-white rounded-md text-sm disabled:opacity-50"
        onClick={submit}
        disabled={loading || !goal.trim()}
      >
        {loading ? "运行中..." : "运行 Agent"}
      </button>

      {error && <div className="mt-4 text-sm text-red-600">{error}</div>}

      {streamText && !run && (
        <div className="mt-6 bg-white border rounded-md p-4">
          <div className="text-xs text-slate-500 mb-1">流式输出</div>
          <div className="text-sm whitespace-pre-wrap">{streamText}</div>
        </div>
      )}

      {run && (
        <div className="mt-6 space-y-3">
          <div className="bg-white border rounded-md p-4">
            <div className="text-xs text-slate-500 mb-1">最终回答（角色：{run.role}）</div>
            <div className="text-sm whitespace-pre-wrap">{run.final_answer}</div>
          </div>
          <details className="bg-white border rounded-md p-4">
            <summary className="text-sm cursor-pointer">事件序列（{run.events.length}）</summary>
            <ol className="mt-2 text-xs space-y-1">
              {run.events.map((e, i) => (
                <li key={i}>
                  [{e.step}] {e.kind}
                  {e.tool ? ` · ${e.tool}` : ""}
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </div>
  );
}
