import type { DramaNodeType, ExecutionStatus, ReviewStatus } from "./canvasTypes";

export const nodeTypeColors: Record<DramaNodeType, string> = {
  需求分析: "#60A5FA",
  梗概: "#A78BFA",
  角色设定: "#F472B6",
  分镜: "#FBBF24",
  关键帧: "#34D399",
  视频: "#22D3EE",
  配音: "#818CF8",
  字幕: "#FB923C",
  配乐: "#2DD4BF",
  剪辑: "#C084FC",
  导出: "#F43F5E",
};

export const executionStatusLabels: Record<ExecutionStatus, string> = {
  pending: "待执行",
  running: "运行中",
  awaiting_approval: "等待审核",
  succeeded: "成功",
  failed: "失败",
  skipped: "跳过",
  compensated: "已补偿",
};

export const reviewStatusLabels: Record<ReviewStatus, string> = {
  unreviewed: "未审核",
  review_required: "待审核",
  approved: "已通过",
  modified: "已修改",
  rejected: "已驳回",
};

export const executionStatusClasses: Record<ExecutionStatus, string> = {
  pending: "bg-neutral-800 text-neutral-400 border-neutral-700",
  running: "bg-blue-500/10 text-blue-300 border-blue-500/30",
  awaiting_approval: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  succeeded: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  failed: "bg-red-500/10 text-red-300 border-red-500/30",
  skipped: "bg-neutral-800 text-neutral-500 border-neutral-700",
  compensated: "bg-purple-500/10 text-purple-300 border-purple-500/30",
};

export const reviewStatusClasses: Record<ReviewStatus, string> = {
  unreviewed: "bg-neutral-800 text-neutral-500 border-neutral-700",
  review_required: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  approved: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  modified: "bg-yellow-500/10 text-yellow-300 border-yellow-500/30",
  rejected: "bg-red-500/10 text-red-300 border-red-500/30",
};
