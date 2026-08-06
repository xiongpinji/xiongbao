import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  canResumeCheckpoint,
  checkpointStatusLabel,
  listCheckpoints,
  resumeCheckpoint,
  rollbackCheckpoint,
  type CheckpointView,
} from "../../api/checkpoints.ts";
import { useConfirm } from "../../hooks/useConfirm.tsx";

function shortId(value: string): string {
  return value.length > 12 ? value.slice(0, 12) : value;
}

function formatTime(value: string): string {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : value;
}

export default function CheckpointTimeline({
  conversationId,
  runId,
  compact = false,
}: {
  conversationId?: string;
  runId?: string;
  compact?: boolean;
}) {
  const { confirm, ConfirmDialog } = useConfirm();
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [taskIds, setTaskIds] = useState<Record<string, string>>({});
  const [sources, setSources] = useState<Record<string, "commit" | "patch">>({});
  const enabled = Boolean(conversationId || runId);
  const query = useQuery({
    queryKey: ["checkpoints", conversationId || "", runId || ""],
    queryFn: () => listCheckpoints({ conversationId, runId }),
    enabled,
    refetchInterval: (state) =>
      state.state.data?.some((item) => ["pending", "running"].includes(item.status))
        ? 2500
        : false,
  });

  const runResume = async (checkpoint: CheckpointView) => {
    const approved = await confirm({
      title: "恢复 checkpoint",
      message: `从 ${checkpoint.checkpoint_id} 创建新的 run？原 checkpoint 历史不会被覆盖。`,
      confirmText: "创建新 run",
    });
    if (!approved) return;
    setBusyId(checkpoint.checkpoint_id);
    setError("");
    try {
      const result = await resumeCheckpoint(checkpoint.checkpoint_id);
      setNotice(`已创建恢复 run ${result.checkpoint.run_id}`);
      await query.refetch();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusyId("");
    }
  };

  const runRollback = async (checkpoint: CheckpointView) => {
    const taskId = (taskIds[checkpoint.checkpoint_id] || "").trim();
    if (!taskId) {
      setError("回滚前必须填写与该 run 关联的开发任务 ID。");
      return;
    }
    const source = sources[checkpoint.checkpoint_id] || "commit";
    const approved = await confirm({
      title: "受控 Git 回滚",
      message: `确认以 ${source} 回滚 checkpoint ${checkpoint.checkpoint_id}？工作区必须干净，成功后会生成新的 Git commit。`,
      confirmText: "执行回滚",
      danger: true,
    });
    if (!approved) return;
    setBusyId(checkpoint.checkpoint_id);
    setError("");
    try {
      const result = await rollbackCheckpoint(
        checkpoint.checkpoint_id,
        taskId,
        source,
      );
      setNotice(`回滚完成：${result.checkpoint.rollback_commit}`);
      await query.refetch();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      await query.refetch();
    } finally {
      setBusyId("");
    }
  };

  if (!enabled) return null;

  const checkpoints = query.data ?? [];
  return (
    <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
      <ConfirmDialog />
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">Checkpoint 时间线</div>
          <div className="mt-1 text-xs text-neutral-500">
            恢复会创建新 run；回滚只接受已验证的开发任务 commit 或受控 patch。
          </div>
        </div>
        <button
          type="button"
          onClick={() => void query.refetch()}
          className="text-xs text-neutral-500 transition hover:text-neutral-300"
        >
          刷新
        </button>
      </div>
      {notice && <div className="mt-3 text-xs text-emerald-400">{notice}</div>}
      {(error || query.error) && (
        <div className="mt-3 text-xs text-red-400">
          {error || (query.error instanceof Error ? query.error.message : "读取失败")}
        </div>
      )}
      {query.isLoading && <div className="mt-3 text-xs text-neutral-500">加载中...</div>}
      {!query.isLoading && checkpoints.length === 0 && (
        <div className="mt-3 text-xs text-neutral-600">暂无 checkpoint。</div>
      )}
      <div className="mt-3 space-y-3">
        {checkpoints.map((checkpoint) => (
          <div
            key={checkpoint.checkpoint_id}
            className="rounded-lg border border-white/[0.06] bg-black/20 p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-mono text-[11px] text-neutral-400">
                {shortId(checkpoint.checkpoint_id)} · step {checkpoint.step}
              </div>
              <span className="rounded-full bg-white/[0.05] px-2 py-0.5 text-[10px] text-neutral-400">
                {checkpointStatusLabel(checkpoint.status)}
              </span>
            </div>
            <div className="mt-2 text-xs text-neutral-500">
              run {shortId(checkpoint.run_id)} · {formatTime(checkpoint.created_at)}
            </div>
            {checkpoint.parent_checkpoint_id && (
              <div className="mt-1 text-[11px] text-blue-300/70">
                恢复来源 {shortId(checkpoint.parent_checkpoint_id)}
              </div>
            )}
            {checkpoint.changed_files.length > 0 && (
              <div className="mt-2 text-[11px] text-neutral-500">
                文件：{checkpoint.changed_files.join("、")}
              </div>
            )}
            {checkpoint.rollback_commit && (
              <div className="mt-2 font-mono text-[11px] text-emerald-400/80">
                rollback commit {checkpoint.rollback_commit}
              </div>
            )}
            {checkpoint.rollback_error && (
              <div className="mt-2 text-[11px] text-red-400/80">
                {checkpoint.rollback_error}
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={
                  busyId === checkpoint.checkpoint_id ||
                  !canResumeCheckpoint(checkpoint.status, checkpoint.resumed_run_id)
                }
                onClick={() => void runResume(checkpoint)}
                className="rounded-md bg-neutral-100 px-3 py-1.5 text-xs font-medium text-black transition hover:bg-white disabled:opacity-40"
              >
                恢复为新 run
              </button>
              {checkpoint.resumed_run_id && (
                <Link
                  to={`/runs/${encodeURIComponent(checkpoint.resumed_run_id)}`}
                  className="text-xs text-blue-300/80 hover:text-blue-200"
                >
                  查看恢复 run
                </Link>
              )}
            </div>
            {!compact && checkpoint.changed_files.length > 0 && (
              <div className="mt-3 grid gap-2 border-t border-white/[0.05] pt-3 sm:grid-cols-[minmax(0,1fr)_110px_auto]">
                <input
                  value={taskIds[checkpoint.checkpoint_id] || ""}
                  onChange={(event) =>
                    setTaskIds((value) => ({
                      ...value,
                      [checkpoint.checkpoint_id]: event.target.value,
                    }))
                  }
                  placeholder="关联开发任务 ID"
                  className="rounded-md border border-white/[0.08] bg-black/20 px-3 py-1.5 text-xs text-neutral-300 outline-none focus:border-white/[0.16]"
                />
                <select
                  value={sources[checkpoint.checkpoint_id] || "commit"}
                  onChange={(event) =>
                    setSources((value) => ({
                      ...value,
                      [checkpoint.checkpoint_id]: event.target.value as "commit" | "patch",
                    }))
                  }
                  className="rounded-md border border-white/[0.08] bg-neutral-900 px-2 py-1.5 text-xs text-neutral-300"
                >
                  <option value="commit">commit</option>
                  <option value="patch">patch</option>
                </select>
                <button
                  type="button"
                  disabled={busyId === checkpoint.checkpoint_id}
                  onClick={() => void runRollback(checkpoint)}
                  className="rounded-md border border-red-500/25 bg-red-500/10 px-3 py-1.5 text-xs text-red-300 transition hover:bg-red-500/15 disabled:opacity-40"
                >
                  受控回滚
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
