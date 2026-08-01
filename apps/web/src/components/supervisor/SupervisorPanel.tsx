import { useState } from "react";
import { Bot, Loader2, Play, Users } from "lucide-react";
import { api } from "../../api/client";

interface WorkerResult {
  task_id: string;
  role: string;
  goal: string;
  status: string;
  result: string;
}

interface SupervisorResponse {
  goal: string;
  strategy: string;
  workers: WorkerResult[];
  synthesis: string;
  elapsed_seconds: number;
}

export default function SupervisorPanel() {
  const [goal, setGoal] = useState("");
  const [roles, setRoles] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SupervisorResponse | null>(null);
  const [error, setError] = useState("");
  // 策略选择
  const [strategy, setStrategy] = useState<{ strategy: string; confidence: number; reason: string } | null>(null);

  const analyzeStrategy = async () => {
    if (!goal.trim()) return;
    try {
      const resp = await api.post("/agents/strategy-select", { goal });
      setStrategy(resp.data);
    } catch {
      setStrategy(null);
    }
  };

  const execute = async () => {
    if (!goal.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const body: Record<string, unknown> = { goal };
      if (roles.trim()) {
        body.roles = roles.split(",").map(r => r.trim()).filter(Boolean);
      }
      const resp = await api.post("/agents/supervisor-run", body);
      setResult(resp.data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "执行失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Users size={24} className="text-[#d6ad62]" />
        <div>
          <h2 className="text-xl font-semibold text-white">多 Agent 协作</h2>
          <p className="text-sm text-neutral-500">Supervisor 模式：LLM 分解 → 并行执行 → 综合</p>
        </div>
      </div>

      {/* 输入区 */}
      <div className="space-y-3 rounded-2xl border border-white/[0.07] bg-white/[0.03] p-5">
        <textarea
          value={goal}
          onChange={e => { setGoal(e.target.value); setStrategy(null); }}
          rows={3}
          className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-white outline-none focus:border-[#d6ad62]/50"
          placeholder="描述你的目标，例如：设计一个电商系统的数据库方案，包含用户、商品、订单三个模块..."
        />
        <div className="flex items-center gap-3">
          <input
            value={roles}
            onChange={e => setRoles(e.target.value)}
            className="flex-1 rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white outline-none focus:border-[#d6ad62]/50"
            placeholder="角色（可选，逗号分隔）：架构师, 前端专家, DBA"
          />
          <button
            onClick={analyzeStrategy}
            className="rounded-xl border border-white/10 px-4 py-2 text-sm text-neutral-400 transition hover:border-[#d6ad62]/40 hover:text-[#d6ad62]"
          >
            分析策略
          </button>
          <button
            onClick={execute}
            disabled={loading || !goal.trim()}
            className="flex items-center gap-2 rounded-xl bg-[#d6ad62] px-5 py-2 text-sm font-medium text-black transition hover:brightness-110 disabled:opacity-50"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            执行
          </button>
        </div>
      </div>

      {/* 策略分析结果 */}
      {strategy && (
        <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-white">推荐策略: <span className="text-[#d6ad62]">{strategy.strategy}</span></span>
            <span className="text-xs text-neutral-500">置信度 {(strategy.confidence * 100).toFixed(0)}%</span>
          </div>
          <p className="mt-1 text-xs text-neutral-500">{strategy.reason}</p>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>
      )}

      {/* 执行结果 */}
      {result && (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-neutral-500">
            <span>耗时 {result.elapsed_seconds?.toFixed(1)}s</span>
            <span>{result.workers?.length || 0} 个 Worker</span>
          </div>

          {/* Worker 进度 */}
          <div className="space-y-2">
            {result.workers?.map((w, i) => (
              <div key={i} className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
                <div className="flex items-center gap-2">
                  <Bot size={14} className="text-[#d6ad62]" />
                  <span className="text-sm font-medium text-white">{w.role}</span>
                  <span className={`ml-auto rounded-full px-2 py-0.5 text-xs ${w.status === "done" ? "bg-green-500/15 text-green-400" : "bg-yellow-500/15 text-yellow-400"}`}>
                    {w.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-neutral-500">{w.goal}</p>
                {w.result && <p className="mt-2 text-sm text-neutral-300 line-clamp-4">{w.result}</p>}
              </div>
            ))}
          </div>

          {/* 综合结果 */}
          {result.synthesis && (
            <div className="rounded-xl border border-[#d6ad62]/20 bg-[#d6ad62]/[0.05] p-4">
              <h4 className="mb-2 text-sm font-medium text-[#d6ad62]">综合结论</h4>
              <p className="whitespace-pre-wrap text-sm text-neutral-200">{result.synthesis}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
