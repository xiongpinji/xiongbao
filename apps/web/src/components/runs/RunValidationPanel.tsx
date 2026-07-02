import type { RunDetail } from "../../api/runtime.ts";

function prettyJson(value: unknown): string {
  if (value == null) return "{}";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function pointerLabel(pointer: Record<string, unknown> | null | undefined, fallback: string): string {
  const label = pointer?.label;
  return typeof label === "string" && label.trim().length > 0 ? label : fallback;
}

function readString(value: unknown): string {
  return typeof value === "string" && value.trim().length > 0 ? value : "—";
}

function readRisks(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : String(item).trim()))
    .filter((item) => item.length > 0);
}

function renderRiskGroup(title: string, risks: string[]) {
  if (!risks.length) {
    return (
      <div className="rounded-2xl border border-dashed border-neutral-700 bg-neutral-900 p-3 text-sm text-neutral-500">
        {title}：无
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-900 p-3">
      <div className="text-xs font-medium uppercase tracking-[0.18em] text-neutral-400">{title}</div>
      <ul className="mt-2 space-y-2 text-sm leading-6 text-neutral-300">
        {risks.map((risk, index) => (
          <li key={`${title}-${risk}-${index}`} className="rounded-2xl border border-neutral-800 bg-neutral-950 px-3 py-2">
            {risk}
          </li>
        ))}
      </ul>
    </div>
  );
}

function renderPointerCard(
  title: string,
  pointer: Record<string, unknown> | null | undefined,
  emptyText: string,
) {
  if (!pointer) {
    return (
      <div className="rounded-2xl border border-dashed border-neutral-700 bg-neutral-950 p-4 text-sm text-neutral-500">
        {emptyText}
      </div>
    );
  }

  return (
    <article className="rounded-2xl border border-neutral-800 bg-neutral-950 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">{title}</div>
          <div className="mt-1 text-xs text-neutral-500">{pointerLabel(pointer, title)}</div>
        </div>
        <div className="rounded-full border border-neutral-700 px-2 py-1 text-[11px] uppercase tracking-[0.18em] text-neutral-400">
          {readString(pointer.mode)}
        </div>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-neutral-500 sm:grid-cols-2">
        <div>
          <span className="text-neutral-400">run</span>
          <div className="mt-1 font-mono text-[11px] text-neutral-300">{readString(pointer.run_id)}</div>
        </div>
        <div>
          <span className="text-neutral-400">step</span>
          <div className="mt-1 font-mono text-[11px] text-neutral-300">{readString(pointer.step_id)}</div>
        </div>
        <div>
          <span className="text-neutral-400">api</span>
          <div className="mt-1 break-all font-mono text-[11px] text-neutral-300">
            {readString(pointer.api_path ?? pointer.approve_path)}
          </div>
        </div>
        <div>
          <span className="text-neutral-400">console</span>
          <div className="mt-1 break-all font-mono text-[11px] text-neutral-300">{readString(pointer.console_path)}</div>
        </div>
      </div>
      {pointer.deny_path ? (
        <div className="mt-2 text-xs text-neutral-500">
          deny <span className="break-all font-mono text-[11px] text-neutral-300">{readString(pointer.deny_path)}</span>
        </div>
      ) : null}
    </article>
  );
}

function RunValidationPanelContent({ detail }: { detail: RunDetail }) {
  const workflowSteps = Array.isArray(detail.workflow?.steps) ? detail.workflow.steps : [];
  const approvalSteps = workflowSteps.filter((step) => step.has_approval);
  const deliveryRisks = readRisks(detail.delivery.risks);
  const validationRisks = readRisks(detail.validation.risks);

  return (
    <section className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">验证 · 风险 · 恢复</div>
          <p className="mt-1 text-xs leading-5 text-neutral-500">
            分开展示验证结果、风险来源以及 replay / resume 恢复指针。
          </p>
        </div>
        <div className="rounded-full border border-neutral-700 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-neutral-400">
          {detail.workflow?.status ?? detail.task?.status ?? "unknown"}
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <section className="rounded-2xl border border-neutral-800 bg-neutral-950 p-4">
          <div className="text-sm font-medium text-white">Validation</div>
          <pre className="mt-3 overflow-auto rounded-2xl border border-neutral-800 bg-neutral-900 p-3 text-xs leading-5 text-neutral-300 whitespace-pre-wrap">
            {prettyJson(detail.validation)}
          </pre>
        </section>

        <section className="rounded-2xl border border-neutral-800 bg-neutral-950 p-4">
          <div className="text-sm font-medium text-white">Risk</div>
          <div className="mt-3 space-y-3">
            {renderRiskGroup("Delivery Risks", deliveryRisks)}
            {renderRiskGroup("Validation Risks", validationRisks)}
          </div>
          <div className="mt-3 text-xs text-neutral-500">
            审批步骤 {approvalSteps.length} 个
            {approvalSteps.length ? ` · ${approvalSteps.map((step) => step.name ?? step.id).join("、")}` : ""}
          </div>
        </section>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div>
          <div className="mb-2 text-sm font-medium text-white">Replay</div>
          {renderPointerCard("Replay", detail.delivery.replay, "暂无 replay 指针。")}
        </div>
        <div>
          <div className="mb-2 text-sm font-medium text-white">Resume</div>
          {renderPointerCard("Resume", detail.delivery.resume, "当前运行无需 resume。")}
        </div>
      </div>
    </section>
  );
}

export default RunValidationPanelContent;
