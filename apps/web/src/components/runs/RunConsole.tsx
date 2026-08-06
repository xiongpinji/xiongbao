import { useState } from "react";
import { isRunTerminal, type RunDetail } from "../../api/runtime.ts";
import CollapsiblePanel from "../layout/CollapsiblePanel.tsx";
import RunValidationPanel from "./RunValidationPanel.tsx";
import RunArtifactsPanel from "./RunArtifactsPanel.tsx";
import RunEvidencePanel from "./RunEvidencePanel.tsx";
import RunTimelinePanel from "./RunTimelinePanel.tsx";
import ConversationalCommand from "../chat/ConversationalCommand.tsx";
import CheckpointTimeline from "../checkpoints/CheckpointTimeline.tsx";

function formatTaskLabel(detail: RunDetail): string {
  const kind = detail.task?.kind || detail.delivery.kind || "runtime.run";
  const status = detail.task?.status || detail.workflow?.status || detail.delivery.status || "unknown";
  return `${kind} · ${status}`;
}

function summaryText(detail: RunDetail): string {
  const deliverySummary = detail.delivery.summary;
  if (typeof deliverySummary === "string" && deliverySummary.trim().length > 0) {
    return deliverySummary;
  }
  if (detail.workflow?.spec_name) {
    return `工作流 ${detail.workflow.spec_name} 的运行详情`;
  }
  if (detail.task?.kind) {
    return `任务 ${detail.task.kind} 的运行详情`;
  }
  return "统一 runtime 运行详情";
}

function prettyJson(value: unknown): string {
  if (value == null) return "{}";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function answerRunQuestion(detail: RunDetail, value: string): string {
  const lower = value.toLowerCase();
  const status = detail.task?.status || detail.workflow?.status || detail.delivery.status || "unknown";
  if (value.includes("失败") || lower.includes("fail")) {
    const failure =
      detail.delivery.failure && typeof detail.delivery.failure === "object"
        ? detail.delivery.failure
        : null;
    const failureReason =
      typeof failure?.reason === "string"
        ? failure.reason
        : typeof failure?.message === "string"
          ? failure.message
          : "";
    const recommendedAction =
      typeof failure?.recommended_action === "string" ? failure.recommended_action : "";
    const blockingStep = typeof failure?.blocking_step === "string" ? failure.blocking_step : "";
    if (failureReason) {
      return `当前运行状态是 ${status}。失败原因：${failureReason}${blockingStep ? `；阻塞位置：${blockingStep}` : ""}${recommendedAction ? `；建议动作：${recommendedAction}` : ""}。`;
    }
    return detail.validation
      ? `当前运行状态是 ${status}。优先检查 Validation 面板和 Timeline 中的失败事件，再按 evidence 追溯具体输入输出。`
      : `当前运行状态是 ${status}。这个运行没有返回独立 validation 结构，先从 Timeline 的异常事件开始定位。`;
  }
  if (value.includes("产物") || lower.includes("artifact")) {
    return `当前运行有 ${detail.artifacts.length} 个产物。可从 Artifacts 面板查看路径、类型和生成状态。`;
  }
  if (value.includes("总结") || value.includes("复盘")) {
    return `${summaryText(detail)}。Timeline ${detail.timeline.length} 条，Evidence ${detail.evidence.length} 条，Artifacts ${detail.artifacts.length} 个，当前状态 ${status}。`;
  }
  return `已收到运行追问：${value}。建议按 Timeline、Evidence、Artifacts 的顺序追踪，避免只看最终状态。`;
}

export default function RunConsole({ detail }: { detail: RunDetail }) {
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const [evidenceCollapsed, setEvidenceCollapsed] = useState(false);
  const [artifactsCollapsed, setArtifactsCollapsed] = useState(false);

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs font-medium tracking-wide text-neutral-500">
              Run Console
              {!isRunTerminal(detail) && (
                <span className="flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-normal text-emerald-300">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  </span>
                  实时刷新中
                </span>
              )}
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white">{detail.run_id}</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-neutral-400">{summaryText(detail)}</p>
          </div>
          <div className="grid gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 text-sm text-neutral-300 sm:grid-cols-2 lg:min-w-[320px]">
            <div>
              <div className="text-xs text-neutral-500">租户</div>
              <div className="mt-1 font-mono text-[11px] text-neutral-300">{detail.tenant_id || "—"}</div>
            </div>
            <div>
              <div className="text-xs text-neutral-500">状态</div>
              <div className="mt-1 text-neutral-100">{formatTaskLabel(detail)}</div>
            </div>
            <div>
              <div className="text-xs text-neutral-500">Timeline</div>
              <div className="mt-1 text-neutral-100">{detail.timeline.length} 条</div>
            </div>
            <div>
              <div className="text-xs text-neutral-500">Artifacts</div>
              <div className="mt-1 text-neutral-100">{detail.artifacts.length} 个</div>
            </div>
          </div>
        </div>
      </section>

      <ConversationalCommand
        title="运行分析助手"
        context={`run ${detail.run_id}`}
        placeholder="询问这个运行的失败原因、产物、证据或下一步修复动作..."
        initialAssistantMessage="我会把运行详情当成一条可追问的会话，按时间线、证据和产物回答。"
        suggestions={[
          "总结这次运行",
          "查找失败原因",
          "列出可交付产物",
        ]}
        onSubmit={(value) => answerRunQuestion(detail, value)}
      />

      <CheckpointTimeline runId={detail.run_id} />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <div className="space-y-4">
          <RunValidationPanel detail={detail} />
          <CollapsiblePanel
            title={`Timeline · ${detail.timeline.length}`}
            collapsed={timelineCollapsed}
            onToggle={() => setTimelineCollapsed((value) => !value)}
          >
            <RunTimelinePanel timeline={detail.timeline} />
          </CollapsiblePanel>
          <CollapsiblePanel
            title={`Evidence · ${detail.evidence.length}`}
            collapsed={evidenceCollapsed}
            onToggle={() => setEvidenceCollapsed((value) => !value)}
          >
            <RunEvidencePanel evidence={detail.evidence} />
          </CollapsiblePanel>
          <CollapsiblePanel
            title={`Artifacts · ${detail.artifacts.length}`}
            collapsed={artifactsCollapsed}
            onToggle={() => setArtifactsCollapsed((value) => !value)}
          >
            <RunArtifactsPanel artifacts={detail.artifacts} />
          </CollapsiblePanel>
        </div>

        <aside className="space-y-4">
          <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="text-sm font-medium text-white">Delivery</div>
            <pre className="mt-3 overflow-auto rounded-lg border border-white/[0.07] bg-black/35 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
              {prettyJson(detail.delivery)}
            </pre>
          </section>

          <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="text-sm font-medium text-white">Validation</div>
            <pre className="mt-3 overflow-auto rounded-lg border border-white/[0.07] bg-black/35 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
              {prettyJson(detail.validation)}
            </pre>
          </section>

          <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="text-sm font-medium text-white">Related Tasks</div>
            {detail.related_tasks.length ? (
              <div className="mt-3 space-y-2">
                {detail.related_tasks.map((task) => (
                  <div key={`${task.task_id}-${task.run_id}`} className="rounded-lg border border-white/[0.07] bg-black/30 p-3">
                    <div className="text-sm text-white">{task.kind}</div>
                    <div className="mt-1 text-xs text-neutral-500">{task.status} · run {task.run_id}</div>
                    <div className="mt-2 font-mono text-[11px] text-neutral-600">task {task.task_id}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-3 text-sm text-neutral-500">暂无关联任务。</div>
            )}
          </section>
        </aside>
      </section>
    </div>
  );
}
