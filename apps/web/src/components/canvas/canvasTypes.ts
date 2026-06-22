export type DramaNodeType =
  | "需求分析"
  | "梗概"
  | "角色设定"
  | "分镜"
  | "关键帧"
  | "视频"
  | "配音"
  | "字幕"
  | "配乐"
  | "剪辑"
  | "导出";

export type ExecutionStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "failed"
  | "skipped"
  | "compensated";

export type ReviewStatus =
  | "unreviewed"
  | "review_required"
  | "approved"
  | "modified"
  | "rejected";

export type ArtifactKind = "text" | "image" | "video" | "audio" | "subtitle" | "timeline" | "draft";

export type GenerationStrategy = "balanced" | "precision" | "creative" | "speed" | "expert";

export interface DramaArtifact {
  id: string;
  kind: ArtifactKind;
  title: string;
  url?: string;
  content?: unknown;
  taskId?: string;
  provider?: string;
  status?: "pending" | "running" | "succeeded" | "failed";
  metadata?: Record<string, unknown>;
}

/**
 * 节点级生成 / 参数设置，参考 X-Agent 视觉工作流的 settings 字段。
 * 所有字段都可选，便于不同节点类型使用不同子集。
 */
export interface DramaNodeSettings {
  prompt?: string;
  negativePrompt?: string;
  model?: string;
  sampler?: string;
  scheduler?: string;
  steps?: number;
  cfg?: number;
  seed?: number;
  resolution?: string;
  duration?: number;
  batch?: number;
  strategy?: GenerationStrategy;
  shotType?: string;
  voice?: string;
  bgmStyle?: string;
  language?: string;
}

export interface ResourceEstimate {
  vramMB?: number;
  timeSeconds?: number;
  difficulty?: "low" | "medium" | "high";
}

export interface QualityReport {
  overall: number;
  connectivity?: number;
  completeness?: number;
  parameters?: number;
  security?: number;
  executability?: number;
  resource?: number;
  issues?: string[];
}

export interface DramaCanvasNodeData {
  nodeId: string;
  nodeType: DramaNodeType;
  title: string;
  content: unknown;
  dependencies: string[];
  reviewStatus: ReviewStatus;
  executionStatus: ExecutionStatus;
  agentNote?: string;
  humanNote?: string;
  artifacts: DramaArtifact[];
  workflowRunId?: string;
  workflowStepId?: string;
  settings?: DramaNodeSettings;
  resourceEstimate?: ResourceEstimate;
  qualityReport?: QualityReport;
  progress?: number; // 0-100
  locked?: boolean;
  onAction?: (nodeId: string, action: CanvasNodeAction) => void;
}

export type CanvasNodeAction =
  // 基础
  | "edit"
  | "rename"
  | "duplicate"
  | "insert-next"
  | "delete"
  | "lock"
  | "unlock"
  // 执行
  | "run"
  | "auto-execute"
  | "rerun-downstream"
  | "stop"
  | "generate"
  // 设置（X-Agent 风格）
  | "configure-prompt"
  | "configure-negative"
  | "configure-model"
  | "configure-sampler"
  | "configure-params"
  | "configure-resolution"
  | "configure-batch"
  | "configure-strategy"
  | "configure-shot"
  | "configure-voice"
  | "configure-bgm"
  | "copy-prompt"
  | "paste-prompt"
  // 审核
  | "approve"
  | "reject"
  | "request-review"
  // 产物
  | "save-asset"
  | "preview-artifact"
  | "download-artifact"
  | "view-history"
  | "view-log"
  // 资源 / 质量
  | "estimate-resource"
  | "quality-report"
  | "auto-fix"
  // 剪辑链路
  | "sync-upstream"
  | "create-timeline"
  | "agent-clip"
  | "render"
  | "export-draft"
  // 数据
  | "export-node-json"
  | "import-node-json";

export type CanvasGlobalAction =
  | "add-node"
  | "parse-script"
  | "auto-layout"
  | "fit-view"
  | "toggle-palette"
  | "run-all"
  | "auto-execute-all"
  | "batch-generate"
  | "resource-estimate-all"
  | "quality-report-all"
  | "global-settings"
  | "import-canvas"
  | "export-canvas"
  | "clear-canvas";

export interface CanvasMenuState {
  kind: "canvas" | "node";
  x: number;
  y: number;
  nodeId?: string;
}

export const DRAMA_NODE_TYPES: DramaNodeType[] = [
  "需求分析",
  "梗概",
  "角色设定",
  "分镜",
  "关键帧",
  "视频",
  "配音",
  "字幕",
  "配乐",
  "剪辑",
  "导出",
];

export const STRATEGY_LABELS: Record<GenerationStrategy, string> = {
  balanced: "平衡",
  precision: "精确",
  creative: "创意",
  speed: "极速",
  expert: "专家",
};

const defaultSamplersByType: Partial<Record<DramaNodeType, DramaNodeSettings>> = {
  关键帧: {
    sampler: "euler_a",
    scheduler: "karras",
    steps: 28,
    cfg: 6.5,
    resolution: "1024x1024",
    batch: 1,
    strategy: "balanced",
  },
  视频: {
    sampler: "dpmpp_2m",
    scheduler: "sgm_uniform",
    steps: 24,
    cfg: 6.0,
    resolution: "1280x720",
    duration: 5,
    batch: 1,
    strategy: "balanced",
  },
  配音: { voice: "female_warm", language: "zh-CN", duration: 6 },
  字幕: { language: "zh-CN" },
  配乐: { bgmStyle: "cinematic", duration: 30 },
  分镜: { shotType: "中景", duration: 4 },
};

export function createDramaNodeData(nodeType: DramaNodeType, index: number): DramaCanvasNodeData {
  const baseSettings = defaultSamplersByType[nodeType] ?? {};
  return {
    nodeId: `${Date.now()}-${index}`,
    nodeType,
    title: `${nodeType}节点`,
    content: getDefaultContent(nodeType),
    dependencies: [],
    reviewStatus: "unreviewed",
    executionStatus: "pending",
    artifacts: [],
    settings: { strategy: "balanced", ...baseSettings, prompt: getDefaultContent(nodeType) },
  };
}

function getDefaultContent(nodeType: DramaNodeType): string {
  const content: Record<DramaNodeType, string> = {
    需求分析: "分析短剧 brief、平台、时长、受众和风格约束。",
    梗概: "生成故事大纲、冲突、反转、高潮和结尾。",
    角色设定: "生成角色卡、角色关系、外貌、服装、声音和提示词。",
    分镜: "拆解镜头、场景、动作、对白和镜头语言。",
    关键帧: "根据分镜和角色设定生成关键帧图片。",
    视频: "根据分镜或关键帧生成视频片段。",
    配音: "生成旁白、角色台词和音频产物。",
    字幕: "生成字幕、校对文本并设置样式。",
    配乐: "生成或选择 BGM、音效和情绪氛围。",
    剪辑: "收集上游产物，创建时间线并合成 clips。",
    导出: "渲染成片并导出剪映草稿。",
  };
  return content[nodeType];
}

/** 返回某节点类型默认显示哪些「设置类」右键项（用于精简菜单噪音） */
export function settingActionsFor(nodeType: DramaNodeType): CanvasNodeAction[] {
  const base: CanvasNodeAction[] = ["configure-prompt", "configure-strategy", "copy-prompt", "paste-prompt"];
  switch (nodeType) {
    case "关键帧":
      return [
        ...base,
        "configure-negative",
        "configure-model",
        "configure-sampler",
        "configure-params",
        "configure-resolution",
        "configure-batch",
      ];
    case "视频":
      return [
        ...base,
        "configure-negative",
        "configure-model",
        "configure-sampler",
        "configure-params",
        "configure-resolution",
        "configure-batch",
      ];
    case "配音":
      return [...base, "configure-voice"];
    case "配乐":
      return [...base, "configure-bgm"];
    case "字幕":
      return [...base];
    case "分镜":
      return [...base, "configure-shot", "configure-batch"];
    default:
      return base;
  }
}
