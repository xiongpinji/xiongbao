import { useState } from "react";
import type { RunDetail } from "../../api/runtime.ts";
import CollapsiblePanel from "../layout/CollapsiblePanel.tsx";
import RunValidationPanel from "./RunValidationPanel.tsx";
import RunArtifactsPanel from "./RunArtifactsPanel.tsx";
import RunEvidencePanel from "./RunEvidencePanel.tsx";
import RunTimelinePanel from "./RunTimelinePanel.tsx";

const previewMessage = "当前分析助手优先基于已加载的运行详情做本地总结，帮助快速查看 Timeline、Evidence 和 Artifacts。";
const initialAssistantMessage = "请基于当前已加载的运行详情回答，优先总结 Timeline、Evidence 与 Artifacts 中已经出现的信息。";

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
          <section className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4 text-sm leading-6 text-cyan-100">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200/80">运行分析助手</div>
            <p className="mt-3">{previewMessage}</p>
            <p className="mt-2 text-cyan-50/90">{initialAssistantMessage}</p>
          </section>

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
