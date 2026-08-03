import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Layers, Lock, Play, RefreshCw, Save, Sliders, Sparkles, Type, Wand2, X } from "lucide-react";
import type { CanvasNodeAction, DramaCanvasNodeData, DramaNodeSettings, GenerationStrategy } from "./canvasTypes";
import { STRATEGY_LABELS } from "./canvasTypes";
import ArtifactPreview from "./ArtifactPreview";
import { nodeTypeColors } from "./canvasTheme";

export default function NodeInspector({
  node,
  onClose,
  onUpdateContent,
  onUpdateSettings,
  onAction,
}: {
  node: DramaCanvasNodeData | null;
  onClose: () => void;
  onUpdateContent: (nodeId: string, content: string, humanNote: string) => void;
  onUpdateSettings?: (nodeId: string, settings: DramaNodeSettings) => void;
  onAction: (nodeId: string, action: CanvasNodeAction) => void;
}) {
  const [content, setContent] = useState("");
  const [humanNote, setHumanNote] = useState("");
  const [settings, setSettings] = useState<DramaNodeSettings>({});
  const [savedFlash, setSavedFlash] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setContent(typeof node?.content === "string" ? node.content : JSON.stringify(node?.content ?? "", null, 2));
    setHumanNote(node?.humanNote ?? "");
    setSettings(node?.settings ?? {});
  }, [node]);

  const color = useMemo(() => (node ? nodeTypeColors[node.nodeType] : "#A3A3A3"), [node]);

  // 切换节点时重置保存闪现
  useEffect(() => () => { if (savedTimer.current) clearTimeout(savedTimer.current); }, []);

  function handleSave() {
    onUpdateContent(node!.nodeId, content, humanNote);
    setSavedFlash(true);
    if (savedTimer.current) clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSavedFlash(false), 1600);
  }

  if (!node) return null;

  const showImageParams = node.nodeType === "关键帧" || node.nodeType === "视频";
  const showVoiceParams = node.nodeType === "配音";
  const showBgmParams = node.nodeType === "配乐";
  const showSubtitleParams = node.nodeType === "字幕";
  const showShotParams = node.nodeType === "分镜";

  const patch = (next: Partial<DramaNodeSettings>) => {
    const merged = { ...settings, ...next };
    setSettings(merged);
    onUpdateSettings?.(node.nodeId, merged);
  };

  return (
    <aside className="flex w-96 shrink-0 flex-col border-l border-neutral-800 bg-neutral-900 text-neutral-100">
      <div className="flex items-start justify-between gap-3 border-b border-neutral-800 px-5 py-4">
        <div>
          <div className="text-xs font-medium" style={{ color }}>{node.nodeType}</div>
          <h2 className="mt-1 text-lg font-semibold text-white">{node.title}</h2>
          <div className="mt-1 text-[11px] text-neutral-500">执行 {node.executionStatus} · 审核 {node.reviewStatus}</div>
        </div>
        <button onClick={onClose} aria-label="关闭面板" className="rounded-lg p-2 text-neutral-500 hover:bg-neutral-800 hover:text-white">
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-auto px-5 py-4">
        <div className="space-y-5">
          <Section title="提示词" icon={Type}>
            <textarea
              className="min-h-28 w-full rounded-lg border border-neutral-700 bg-neutral-950 p-3 text-sm leading-6 text-neutral-100 outline-none focus:border-neutral-500"
              value={settings.prompt ?? ""}
              placeholder="正向提示词，例如：电影感、写实风、暖光…"
              onChange={(event) => patch({ prompt: event.target.value })}
            />
            <textarea
              className="mt-2 min-h-16 w-full rounded-lg border border-neutral-700 bg-neutral-950 p-3 text-xs leading-6 text-neutral-300 outline-none focus:border-neutral-500"
              value={settings.negativePrompt ?? ""}
              placeholder="负面提示词（可选）"
              onChange={(event) => patch({ negativePrompt: event.target.value })}
            />
          </Section>

          <Section title="生成策略" icon={Wand2}>
            <div className="grid grid-cols-5 gap-1">
              {(Object.keys(STRATEGY_LABELS) as GenerationStrategy[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => patch({ strategy: key })}
                  className={`rounded-lg border px-2 py-1.5 text-[11px] transition ${
                    settings.strategy === key
                      ? "border-blue-500/60 bg-blue-500/15 text-blue-200"
                      : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:bg-neutral-800"
                  }`}
                >
                  {STRATEGY_LABELS[key]}
                </button>
              ))}
            </div>
          </Section>

          {showImageParams ? (
            <Section title="采样参数" icon={Sliders}>
              <div className="grid grid-cols-2 gap-2">
                <Field label="模型">
                  <input
                    className="field-mini w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.model ?? ""}
                    placeholder="sdxl_base / wan2.2…"
                    onChange={(event) => patch({ model: event.target.value })}
                  />
                </Field>
                <Field label="分辨率">
                  <select
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.resolution ?? ""}
                    onChange={(event) => patch({ resolution: event.target.value })}
                  >
                    <option value="">默认</option>
                    <option>768x768</option>
                    <option>1024x1024</option>
                    <option>1280x720</option>
                    <option>1920x1080</option>
                  </select>
                </Field>
                <Field label="Sampler">
                  <input
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.sampler ?? ""}
                    placeholder="euler_a / dpmpp_2m"
                    onChange={(event) => patch({ sampler: event.target.value })}
                  />
                </Field>
                <Field label="Scheduler">
                  <input
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.scheduler ?? ""}
                    placeholder="karras / sgm_uniform"
                    onChange={(event) => patch({ scheduler: event.target.value })}
                  />
                </Field>
                <Field label="Steps">
                  <input
                    type="number"
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.steps ?? ""}
                    onChange={(event) => patch({ steps: numberOrUndefined(event.target.value) })}
                  />
                </Field>
                <Field label="CFG">
                  <input
                    type="number"
                    step="0.1"
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.cfg ?? ""}
                    onChange={(event) => patch({ cfg: numberOrUndefined(event.target.value) })}
                  />
                </Field>
                <Field label="Seed">
                  <input
                    type="number"
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.seed ?? ""}
                    onChange={(event) => patch({ seed: numberOrUndefined(event.target.value) })}
                  />
                </Field>
                <Field label="批量">
                  <input
                    type="number"
                    min={1}
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.batch ?? ""}
                    onChange={(event) => patch({ batch: numberOrUndefined(event.target.value) })}
                  />
                </Field>
                {node.nodeType === "视频" ? (
                  <Field label="时长(秒)">
                    <input
                      type="number"
                      min={1}
                      className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                      value={settings.duration ?? ""}
                      onChange={(event) => patch({ duration: numberOrUndefined(event.target.value) })}
                    />
                  </Field>
                ) : null}
              </div>
            </Section>
          ) : null}

          {showVoiceParams ? (
            <Section title="配音参数" icon={Sliders}>
              <div className="grid grid-cols-2 gap-2">
                <Field label="音色">
                  <input
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.voice ?? ""}
                    placeholder="female_warm / male_calm"
                    onChange={(event) => patch({ voice: event.target.value })}
                  />
                </Field>
                <Field label="语言">
                  <select
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.language ?? "zh-CN"}
                    onChange={(event) => patch({ language: event.target.value })}
                  >
                    <option value="zh-CN">中文 (普通话)</option>
                    <option value="en-US">英文</option>
                  </select>
                </Field>
                <Field label="时长(秒)">
                  <input
                    type="number"
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.duration ?? ""}
                    onChange={(event) => patch({ duration: numberOrUndefined(event.target.value) })}
                  />
                </Field>
              </div>
            </Section>
          ) : null}

          {showBgmParams ? (
            <Section title="BGM 参数" icon={Sliders}>
              <div className="grid grid-cols-2 gap-2">
                <Field label="风格">
                  <input
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.bgmStyle ?? ""}
                    placeholder="cinematic / lofi / epic"
                    onChange={(event) => patch({ bgmStyle: event.target.value })}
                  />
                </Field>
                <Field label="时长(秒)">
                  <input
                    type="number"
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.duration ?? ""}
                    onChange={(event) => patch({ duration: numberOrUndefined(event.target.value) })}
                  />
                </Field>
              </div>
            </Section>
          ) : null}

          {showSubtitleParams ? (
            <Section title="字幕参数" icon={Sliders}>
              <Field label="语言">
                <select
                  className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                  value={settings.language ?? "zh-CN"}
                  onChange={(event) => patch({ language: event.target.value })}
                >
                  <option value="zh-CN">中文</option>
                  <option value="en-US">英文</option>
                </select>
              </Field>
            </Section>
          ) : null}

          {showShotParams ? (
            <Section title="分镜参数" icon={Sliders}>
              <div className="grid grid-cols-2 gap-2">
                <Field label="镜头类型">
                  <select
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.shotType ?? ""}
                    onChange={(event) => patch({ shotType: event.target.value })}
                  >
                    <option value="">默认</option>
                    <option>特写</option>
                    <option>近景</option>
                    <option>中景</option>
                    <option>全景</option>
                    <option>远景</option>
                  </select>
                </Field>
                <Field label="单镜时长(秒)">
                  <input
                    type="number"
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.duration ?? ""}
                    onChange={(event) => patch({ duration: numberOrUndefined(event.target.value) })}
                  />
                </Field>
                <Field label="镜头数">
                  <input
                    type="number"
                    className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
                    value={settings.batch ?? ""}
                    onChange={(event) => patch({ batch: numberOrUndefined(event.target.value) })}
                  />
                </Field>
              </div>
            </Section>
          ) : null}

          <Section title="人工备注 / 原始内容" icon={Type}>
            <textarea
              className="min-h-20 w-full rounded-lg border border-neutral-700 bg-neutral-950 p-3 text-sm leading-6 text-neutral-100 outline-none focus:border-neutral-500"
              value={humanNote}
              placeholder="人工备注"
              onChange={(event) => setHumanNote(event.target.value)}
            />
            <textarea
              className="mt-2 min-h-28 w-full rounded-lg border border-neutral-800 bg-neutral-950 p-3 text-xs leading-6 text-neutral-400 outline-none focus:border-neutral-600"
              value={content}
              placeholder="原始节点内容（JSON 或文本）"
              onChange={(event) => setContent(event.target.value)}
            />
          </Section>

          {node.resourceEstimate ? (
            <Section title="资源估算" icon={Layers}>
              <div className="flex flex-wrap gap-2 text-[11px] text-neutral-300">
                {typeof node.resourceEstimate.vramMB === "number" ? (
                  <Chip>显存 ~{node.resourceEstimate.vramMB}MB</Chip>
                ) : null}
                {typeof node.resourceEstimate.timeSeconds === "number" ? (
                  <Chip>时间 ~{Math.round(node.resourceEstimate.timeSeconds)}s</Chip>
                ) : null}
                {node.resourceEstimate.difficulty ? <Chip>难度 {node.resourceEstimate.difficulty}</Chip> : null}
              </div>
            </Section>
          ) : null}

          {node.qualityReport ? (
            <Section title="质量评估" icon={Sparkles}>
              <div className="flex items-center justify-between text-xs">
                <span className="text-neutral-400">总分</span>
                <span className="font-mono text-emerald-300">{Math.round(node.qualityReport.overall)} / 100</span>
              </div>
              {node.qualityReport.issues?.length ? (
                <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-red-300">
                  {node.qualityReport.issues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              ) : null}
            </Section>
          ) : null}

          <Section title="产物" icon={Layers}>
            <ArtifactPreview artifacts={node.artifacts} />
          </Section>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-neutral-800 px-5 py-3">
        <ActionButton onClick={handleSave} icon={savedFlash ? Check : Save} highlight={savedFlash}>{savedFlash ? "已保存" : "保存"}</ActionButton>
        <ActionButton onClick={() => onAction(node.nodeId, "run")} icon={Play}>运行</ActionButton>
        <ActionButton onClick={() => onAction(node.nodeId, "generate")} icon={RefreshCw}>生成</ActionButton>
        <ActionButton onClick={() => onAction(node.nodeId, "approve")} icon={Check}>通过</ActionButton>
        <ActionButton onClick={() => onAction(node.nodeId, "reject")} icon={X}>驳回</ActionButton>
        <ActionButton onClick={() => onAction(node.nodeId, node.locked ? "unlock" : "lock")} icon={Lock}>
          {node.locked ? "解锁" : "锁定"}
        </ActionButton>
      </div>
    </aside>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: typeof Type; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-neutral-500">
        <Icon size={12} />
        {title}
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-neutral-500">{label}</span>
      {children}
    </label>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-neutral-700 bg-neutral-800/60 px-2 py-0.5 text-[11px] text-neutral-300">
      {children}
    </span>
  );
}

function ActionButton({ children, icon: Icon, onClick, highlight }: { children: React.ReactNode; icon: typeof Save; onClick: () => void; highlight?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition active:scale-[0.98] ${
        highlight
          ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
          : "border-neutral-700 text-neutral-200 hover:bg-neutral-800 hover:text-white"
      }`}
    >
      <Icon size={14} />
      {children}
    </button>
  );
}

function numberOrUndefined(value: string): number | undefined {
  if (!value) return undefined;
  const num = Number(value);
  return Number.isFinite(num) ? num : undefined;
}
