import { useState } from "react";
import type { RunDetail, RuntimeDeliveryFailure } from "../../api/runtime.ts";
import CollapsiblePanel from "../layout/CollapsiblePanel.tsx";
import RunValidationPanel from "./RunValidationPanel.tsx";
import RunArtifactsPanel from "./RunArtifactsPanel.tsx";
import RunEvidencePanel from "./RunEvidencePanel.tsx";
import RunTimelinePanel from "./RunTimelinePanel.tsx";

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

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : String(item).trim()))
    .filter((item) => item.length > 0);
}

function readFailure(detail: RunDetail): RuntimeDeliveryFailure | null {
  const value = detail.delivery.failure;
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : null;
}

function renderFailureSummary(detail: RunDetail) {
  const failure = readFailure(detail);
  if (!failure) {
    return null;
  }

  const suggestedActions = readStringList(failure.suggested_repair_actions);
  const escalationPath = typeof failure.escalation_path === "string" ? failure.escalation_path : "";

  return (
    <section className="rounded-3xl border border-amber-500/40 bg-amber-500/10 p-6 shadow-2xl shadow-black/20">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-[0.24em] text-amber-200">Failure Delivery</div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-amber-50">{String(failure.message || "交付已阻塞")}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-amber-100/80">
            当前运行已经进入失败态，请先处理阻塞原因，再继续 replay 或重试。
          </p>
        </div>
        <div className="rounded-2xl border border-amber-400/30 bg-neutral-950/70 px-4 py-3 text-sm text-amber-100">
          <div className="text-xs text-amber-200/80">升级路径</div>
          <div className="mt-1 font-mono text-[11px] text-amber-50">{escalationPath || "—"}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        <section className="rounded-2xl border border-amber-500/20 bg-neutral-950/70 p-4">
          <div className="text-sm font-medium text-amber-50">建议动作</div>
          {suggestedActions.length ? (
            <ul className="mt-3 space-y-2 text-sm leading-6 text-amber-100/90">
              {suggestedActions.map((action, index) => (
                <li key={`${action}-${index}`} className="rounded-2xl border border-neutral-800 bg-neutral-950 px-3 py-2">
                  {action}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-3 text-sm text-amber-100/70">暂无建议动作。</div>
          )}
        </section>

        <section className="rounded-2xl border border-amber-500/20 bg-neutral-950/70 p-4">
          <div className="text-sm font-medium text-amber-50">Failure JSON</div>
          <pre className="mt-3 overflow-auto rounded-2xl border border-neutral-800 bg-neutral-950 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
            {prettyJson(failure)}
          </pre>
        </section>
      </div>
    </section>
  );
}

export default function RunConsole({ detail }: { detail: RunDetail }) {
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const [evidenceCollapsed, setEvidenceCollapsed] = useState(false);
  const [artifactsCollapsed, setArtifactsCollapsed] = useState(false);

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-neutral-800 bg-neutral-900 p-6 shadow-2xl shadow-black/20">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-[0.24em] text-neutral-500">Run Console</div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white">{detail.run_id}</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-neutral-400">{summaryText(detail)}</p>
          </div>
          <div className="grid gap-3 rounded-2xl border border-neutral-800 bg-neutral-950 p-4 text-sm text-neutral-300 sm:grid-cols-2 lg:min-w-[320px]">
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

      {renderFailureSummary(detail)}

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
          <section className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="text-sm font-medium text-white">Delivery</div>
            <pre className="mt-3 overflow-auto rounded-2xl border border-neutral-800 bg-neutral-950 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
              {prettyJson(detail.delivery)}
            </pre>
          </section>

          <section className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="text-sm font-medium text-white">Validation</div>
            <pre className="mt-3 overflow-auto rounded-2xl border border-neutral-800 bg-neutral-950 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
              {prettyJson(detail.validation)}
            </pre>
          </section>

          <section className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="text-sm font-medium text-white">Related Tasks</div>
            {detail.related_tasks.length ? (
              <div className="mt-3 space-y-2">
                {detail.related_tasks.map((task) => (
                  <div key={`${task.task_id}-${task.run_id}`} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-3">
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
