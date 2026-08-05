import {
  CheckCircle2,
  Clock,
  Cpu,
  FileText,
  Image,
  Layers,
  Lock,
  Mic,
  Music,
  Scissors,
  Send,
  Sparkles,
  Subtitles,
  Video,
} from "lucide-react";
import { Handle, Position } from "reactflow";
import type { DramaArtifact, DramaCanvasNodeData, DramaNodeType } from "./canvasTypes";
import {
  executionStatusClasses,
  executionStatusLabels,
  nodeTypeColors,
  reviewStatusClasses,
  reviewStatusLabels,
} from "./canvasTheme";

const iconMap: Record<DramaNodeType, typeof FileText> = {
  需求分析: FileText,
  梗概: FileText,
  角色设定: FileText,
  分镜: FileText,
  关键帧: Image,
  视频: Video,
  配音: Mic,
  字幕: Subtitles,
  配乐: Music,
  剪辑: Scissors,
  导出: Send,
};

export default function CanvasNodeCard({ data }: { data: DramaCanvasNodeData }) {
  const color = nodeTypeColors[data.nodeType];
  const Icon = iconMap[data.nodeType];
  const content = typeof data.content === "string" ? data.content : JSON.stringify(data.content ?? "");
  const isRunning = data.executionStatus === "running";
  const isLocked = Boolean(data.locked);
  const progress = typeof data.progress === "number" ? Math.max(0, Math.min(100, data.progress)) : null;

  const settingsBadges = collectSettingsBadges(data);

  return (
    <div
      tabIndex={0}
      role="button"
      aria-label={`${data.title}，${data.nodeType}节点，执行状态${data.executionStatus}，审核状态${data.reviewStatus}`}
      className={`w-72 rounded-lg border bg-neutral-900 p-4 text-neutral-100 shadow-2xl transition focus:outline-none focus:ring-2 focus:ring-neutral-500 hover:bg-neutral-850 ${
        isRunning ? "shadow-[0_0_0_2px_rgba(59,130,246,0.35)]" : "shadow-black/20"
      }`}
      style={{ borderColor: `${color}99` }}
    >
      <Handle
        id={`${data.nodeId}-in`}
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !rounded-full !border !border-neutral-600 !bg-neutral-950 hover:!bg-blue-400"
      />
      <Handle
        id={`${data.nodeId}-out`}
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !rounded-full !border !border-neutral-600 !bg-neutral-950 hover:!bg-emerald-400"
      />

      {/* 头部 */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-neutral-800" style={{ color }}>
            <Icon size={18} strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1 truncate text-sm font-semibold text-white">
              {data.title}
              {isLocked ? <Lock size={11} className="text-amber-400" aria-label="已锁定" /> : null}
            </div>
            <div className="text-xs" style={{ color }}>{data.nodeType}</div>
          </div>
        </div>
        {data.qualityReport ? <QualityBadge score={data.qualityReport.overall} /> : null}
      </div>

      {/* 正文 */}
      <div className="line-clamp-3 min-h-12 text-xs leading-5 text-neutral-400">{content}</div>

      {/* 进度条（运行中或有进度时显示） */}
      {progress !== null && (isRunning || progress < 100) ? (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-neutral-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-blue-500 to-purple-500 transition-[width]"
            style={{ width: `${progress}%` }}
          />
        </div>
      ) : null}

      {/* 状态徽章行 */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        <span className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${executionStatusClasses[data.executionStatus]}`}>
          {data.executionStatus === "succeeded" ? <CheckCircle2 size={10} /> : null}
          {executionStatusLabels[data.executionStatus]}
        </span>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${reviewStatusClasses[data.reviewStatus]}`}>
          {reviewStatusLabels[data.reviewStatus]}
        </span>
        {data.artifacts.length > 0 && (
          <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[11px] text-cyan-300">
            产物 {data.artifacts.length}
          </span>
        )}
        {settingsBadges.map((badge) => (
          <span
            key={badge.label}
            className="flex items-center gap-1 rounded-full border border-neutral-700 bg-neutral-800/60 px-2 py-0.5 text-[11px] text-neutral-300"
          >
            {badge.icon}
            {badge.label}
          </span>
        ))}
      </div>

      {/* 资源估算 */}
      {data.resourceEstimate ? <ResourceRow estimate={data.resourceEstimate} /> : null}

      {/* 产物缩略 */}
      {data.artifacts.length > 0 ? <ArtifactStrip artifacts={data.artifacts.slice(0, 4)} /> : null}
    </div>
  );
}

function QualityBadge({ score }: { score: number }) {
  const rounded = Math.round(score);
  const color = rounded >= 80 ? "#34D399" : rounded >= 60 ? "#FBBF24" : "#F87171";
  return (
    <div
      className="flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]"
      style={{ color, borderColor: `${color}40`, background: `${color}10` }}
      title={`整体质量 ${rounded}/100`}
    >
      <Sparkles size={10} />
      {rounded}
    </div>
  );
}

function ResourceRow({ estimate }: { estimate: NonNullable<DramaCanvasNodeData["resourceEstimate"]> }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-neutral-400">
      {typeof estimate.vramMB === "number" ? (
        <span className="flex items-center gap-1">
          <Cpu size={11} className="text-blue-300" />
          {estimate.vramMB}MB 显存
        </span>
      ) : null}
      {typeof estimate.timeSeconds === "number" ? (
        <span className="flex items-center gap-1">
          <Clock size={11} className="text-amber-300" />~{Math.round(estimate.timeSeconds)}s
        </span>
      ) : null}
      {estimate.difficulty ? (
        <span className="flex items-center gap-1 text-neutral-500">
          难度：{difficultyLabel(estimate.difficulty)}
        </span>
      ) : null}
    </div>
  );
}

function difficultyLabel(level: "low" | "medium" | "high") {
  if (level === "high") return "高";
  if (level === "medium") return "中";
  return "低";
}

function ArtifactStrip({ artifacts }: { artifacts: DramaArtifact[] }) {
  return (
    <div className="mt-3 flex gap-1.5">
      {artifacts.map((artifact) => (
        <div
          key={artifact.id}
          className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-lg border border-neutral-800 bg-neutral-950 text-[10px] text-neutral-500"
          title={artifact.title}
        >
          {artifact.url && artifact.kind === "image" ? (
            <img src={artifact.url} alt={artifact.title} className="h-full w-full object-cover" />
          ) : (
            <ArtifactIcon kind={artifact.kind} />
          )}
        </div>
      ))}
    </div>
  );
}

function ArtifactIcon({ kind }: { kind: DramaArtifact["kind"] }) {
  switch (kind) {
    case "image":
      return <Image size={14} className="text-emerald-300" />;
    case "video":
      return <Video size={14} className="text-cyan-300" />;
    case "audio":
      return <Mic size={14} className="text-indigo-300" />;
    case "subtitle":
      return <Subtitles size={14} className="text-amber-300" />;
    case "timeline":
      return <Scissors size={14} className="text-purple-300" />;
    case "draft":
      return <Send size={14} className="text-rose-300" />;
    default:
      return <FileText size={14} className="text-neutral-400" />;
  }
}

function collectSettingsBadges(data: DramaCanvasNodeData) {
  const badges: { label: string; icon: JSX.Element }[] = [];
  const settings = data.settings;
  if (!settings) return badges;

  if (settings.batch && settings.batch > 1) {
    badges.push({ label: `×${settings.batch}`, icon: <Layers size={10} /> });
  }
  if (settings.resolution) {
    badges.push({ label: settings.resolution, icon: <Image size={10} /> });
  }
  if (settings.duration && (data.nodeType === "视频" || data.nodeType === "配音" || data.nodeType === "配乐")) {
    badges.push({ label: `${settings.duration}s`, icon: <Clock size={10} /> });
  }
  if (settings.model) {
    badges.push({ label: settings.model, icon: <Sparkles size={10} /> });
  }
  if (settings.shotType && data.nodeType === "分镜") {
    badges.push({ label: settings.shotType, icon: <FileText size={10} /> });
  }
  if (settings.voice && data.nodeType === "配音") {
    badges.push({ label: settings.voice, icon: <Mic size={10} /> });
  }
  return badges;
}
