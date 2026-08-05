import type { CSSProperties, ReactNode } from "react";
import { useEffect, useState } from "react";
import {
  ChevronRight,
  Copy,
  Crop,
  Download,
  Edit3,
  Eye,
  FileJson,
  FileText,
  FilmIcon,
  History,
  Image as ImageIcon,
  Layers,
  Lightbulb,
  Lock,
  Mic,
  Music,
  Palette,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Settings,
  Settings2,
  Sparkles,
  Square,
  Sliders,
  Trash2,
  Type,
  Upload,
  Video as VideoIcon,
  Wand2,
  Workflow,
  Wrench,
  ZapOff,
} from "lucide-react";
import type {
  CanvasGlobalAction,
  CanvasMenuState,
  CanvasNodeAction,
  DramaCanvasNodeData,
  DramaNodeType,
} from "./canvasTypes";
import { DRAMA_NODE_TYPES, settingActionsFor } from "./canvasTypes";
import { useEscapeClose } from "../../hooks/useEscapeClose";

type IconCmp = typeof Edit3;

interface NodeMenuEntry {
  label: string;
  action: CanvasNodeAction;
  icon: IconCmp;
  danger?: boolean;
  shortcut?: string;
}

interface GlobalMenuEntry {
  label: string;
  action: CanvasGlobalAction;
  icon: IconCmp;
  shortcut?: string;
}

interface NodeMenuGroup {
  title: string;
  items: NodeMenuEntry[];
}

const SETTING_LABELS: Record<string, { label: string; icon: IconCmp }> = {
  "configure-prompt": { label: "编辑提示词…", icon: Type },
  "configure-negative": { label: "编辑负面提示词…", icon: ZapOff },
  "configure-model": { label: "切换模型…", icon: Sparkles },
  "configure-sampler": { label: "采样器 / 调度器…", icon: Sliders },
  "configure-params": { label: "Steps / CFG / Seed…", icon: Settings2 },
  "configure-resolution": { label: "分辨率…", icon: Crop },
  "configure-batch": { label: "批量数量…", icon: Layers },
  "configure-strategy": { label: "生成策略…", icon: Lightbulb },
  "configure-shot": { label: "镜头语言…", icon: FilmIcon },
  "configure-voice": { label: "音色 / 语言…", icon: Mic },
  "configure-bgm": { label: "BGM 风格 / 时长…", icon: Music },
  "copy-prompt": { label: "复制提示词", icon: Copy },
  "paste-prompt": { label: "从剪贴板粘贴提示词", icon: Upload },
};

const PER_TYPE_ACCENT: Partial<Record<DramaNodeType, IconCmp>> = {
  关键帧: ImageIcon,
  视频: VideoIcon,
  配音: Mic,
  字幕: Type,
  配乐: Music,
  剪辑: FilmIcon,
  导出: Download,
};

export default function CanvasContextMenu({
  menu,
  onClose,
  onAddNode,
  onNodeAction,
  onCanvasAction,
  selectedNode,
}: {
  menu: CanvasMenuState | null;
  onClose: () => void;
  onAddNode: (type: DramaNodeType) => void;
  onNodeAction: (action: CanvasNodeAction) => void;
  onCanvasAction?: (action: CanvasGlobalAction) => void;
  selectedNode?: DramaCanvasNodeData | null;
}) {
  // 钩子必须在任何提前 return 之前调用（rules of hooks），避免 menu 切换时 hook 数量变化导致崩溃
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight });

  useEffect(() => {
    const onResize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Esc 关闭右键菜单（键盘可达性）
  useEscapeClose(Boolean(menu), onClose);

  if (!menu) return null;

  const positionStyle: CSSProperties = {
    left: clampPosition(menu.x, viewport.width, 340),
    top: clampPosition(menu.y, viewport.height, menu.kind === "canvas" ? 640 : 720),
  };

  return (
    <div className="fixed inset-0 z-50" onClick={onClose} onContextMenu={(event) => event.preventDefault()}>
      <div
        role="menu"
        aria-label={menu.kind === "canvas" ? "画布菜单" : "节点菜单"}
        className="absolute min-w-72 max-w-80 rounded-lg border border-neutral-700/80 bg-neutral-900/95 p-2 text-sm text-neutral-200 shadow-2xl shadow-black/40 backdrop-blur"
        style={positionStyle}
        onClick={(event) => event.stopPropagation()}
      >
        {menu.kind === "canvas" ? (
          <CanvasMenu onAddNode={onAddNode} onClose={onClose} onCanvasAction={onCanvasAction} />
        ) : (
          <NodeMenu node={selectedNode} onAction={onNodeAction} onClose={onClose} />
        )}
      </div>
    </div>
  );
}

function clampPosition(value: number, viewportSize: number, menuSize: number) {
  return Math.max(8, Math.min(value, viewportSize - menuSize - 8));
}

function CanvasMenu({
  onAddNode,
  onClose,
  onCanvasAction,
}: {
  onAddNode: (type: DramaNodeType) => void;
  onClose: () => void;
  onCanvasAction?: (action: CanvasGlobalAction) => void;
}) {
  const dispatchGlobal = (action: CanvasGlobalAction) => {
    onCanvasAction?.(action);
    onClose();
  };

  const groups: { title: string; items: GlobalMenuEntry[] }[] = [
    {
      title: "工作流编排",
      items: [
        { label: "解析剧本…", action: "parse-script", icon: FileText },
        { label: "自动整理布局", action: "auto-layout", icon: Workflow, shortcut: "Shift+L" },
        { label: "适应视图", action: "fit-view", icon: Eye, shortcut: "Shift+F" },
        { label: "展开 / 折叠节点库", action: "toggle-palette", icon: Palette },
      ],
    },
    {
      title: "批量执行",
      items: [
        { label: "运行整张画布", action: "run-all", icon: Play, shortcut: "Shift+R" },
        { label: "全自动执行", action: "auto-execute-all", icon: Wand2 },
        { label: "批量生成关键帧 / 视频", action: "batch-generate", icon: Layers },
      ],
    },
    {
      title: "评估与诊断",
      items: [
        { label: "全局资源估算", action: "resource-estimate-all", icon: Settings },
        { label: "质量评估报告", action: "quality-report-all", icon: Sparkles },
        { label: "全局参数 / 默认设置…", action: "global-settings", icon: Settings2 },
      ],
    },
    {
      title: "数据",
      items: [
        { label: "导入画布 JSON", action: "import-canvas", icon: Upload },
        { label: "导出画布 JSON", action: "export-canvas", icon: FileJson },
        { label: "清空画布", action: "clear-canvas", icon: Trash2 },
      ],
    },
  ];

  return (
    <div>
      <MenuTitle>添加节点</MenuTitle>
      <div className="grid max-h-64 grid-cols-2 gap-1 overflow-auto py-1">
        {DRAMA_NODE_TYPES.map((type) => {
          const Icon = PER_TYPE_ACCENT[type] ?? FileText;
          return (
            <MenuItem
              key={type}
              icon={Icon}
              onClick={() => {
                onAddNode(type);
                onClose();
              }}
            >
              {type}
            </MenuItem>
          );
        })}
      </div>
      {groups.map((group) => (
        <div key={group.title}>
          <MenuDivider />
          <MenuTitle>{group.title}</MenuTitle>
          {group.items.map((item) => (
            <MenuItem
              key={item.action}
              icon={item.icon}
              shortcut={item.shortcut}
              onClick={() => dispatchGlobal(item.action)}
            >
              {item.label}
            </MenuItem>
          ))}
        </div>
      ))}
    </div>
  );
}

function NodeMenu({
  node,
  onAction,
  onClose,
}: {
  node?: DramaCanvasNodeData | null;
  onAction: (action: CanvasNodeAction) => void;
  onClose: () => void;
}) {
  const isLocked = Boolean(node?.locked);
  const groups = buildNodeGroups(node, isLocked);

  const dispatch = (action: CanvasNodeAction) => {
    onAction(action);
    onClose();
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-2 px-3 pb-1 pt-2">
        <div className="flex min-w-0 items-center gap-2">
          {node ? <NodeBadge node={node} /> : null}
          <div className="min-w-0">
            <div className="truncate text-xs font-medium text-white">
              {node?.title ?? "节点操作"}
            </div>
            <div className="text-[11px] text-neutral-500">
              {node ? `${node.nodeType} · ${node.executionStatus}` : "右键节点的可用操作"}
            </div>
          </div>
        </div>
        {isLocked ? (
          <span className="flex shrink-0 items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300">
            <Lock size={10} />
            已锁定
          </span>
        ) : null}
      </div>
      {groups.map((group, idx) => (
        <div key={group.title}>
          {idx === 0 ? <MenuDivider /> : null}
          <MenuTitle>{group.title}</MenuTitle>
          {group.items.map((item) => (
            <MenuItem
              key={item.action}
              icon={item.icon}
              danger={item.danger}
              shortcut={item.shortcut}
              onClick={() => dispatch(item.action)}
            >
              {item.label}
            </MenuItem>
          ))}
          {idx < groups.length - 1 ? <MenuDivider /> : null}
        </div>
      ))}
    </div>
  );
}

function NodeBadge({ node }: { node: DramaCanvasNodeData }) {
  const Icon = PER_TYPE_ACCENT[node.nodeType] ?? FileText;
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-neutral-800 text-neutral-200">
      <Icon size={14} />
    </div>
  );
}

function buildNodeGroups(node: DramaCanvasNodeData | null | undefined, isLocked: boolean): NodeMenuGroup[] {
  const groups: NodeMenuGroup[] = [];

  groups.push({
    title: "基础",
    items: [
      { label: "编辑节点", action: "edit", icon: Edit3, shortcut: "Enter" },
      { label: "重命名", action: "rename", icon: Type, shortcut: "F2" },
      { label: "复制节点", action: "duplicate", icon: Copy, shortcut: "Ctrl+D" },
      { label: "插入后续节点", action: "insert-next", icon: ChevronRight },
      ...(isLocked
        ? [{ label: "解锁节点", action: "unlock" as CanvasNodeAction, icon: Lock }]
        : [{ label: "锁定节点", action: "lock" as CanvasNodeAction, icon: Lock }]),
    ],
  });

  groups.push({
    title: "执行",
    items: [
      { label: "运行此节点", action: "run", icon: Play, shortcut: "Shift+R" },
      { label: "全自动执行", action: "auto-execute", icon: Wand2 },
      { label: "生成 / 重新生成", action: "generate", icon: RefreshCw },
      { label: "重新运行下游", action: "rerun-downstream", icon: RotateCcw },
      { label: "停止本节点", action: "stop", icon: Square },
    ],
  });

  // 节点级设置
  if (node) {
    const settingActions = settingActionsFor(node.nodeType);
    if (settingActions.length) {
      groups.push({
        title: "节点设置",
        items: settingActions.map((action) => {
          const meta = SETTING_LABELS[action];
          return {
            label: meta?.label ?? action,
            action,
            icon: meta?.icon ?? Settings2,
          } satisfies NodeMenuEntry;
        }),
      });
    }
  } else {
    groups.push({
      title: "节点设置",
      items: Object.keys(SETTING_LABELS).map((key) => {
        const meta = SETTING_LABELS[key];
        return { label: meta.label, action: key as CanvasNodeAction, icon: meta.icon };
      }),
    });
  }

  groups.push({
    title: "审核",
    items: [
      { label: "审核通过", action: "approve", icon: Save },
      { label: "驳回重做", action: "reject", icon: RotateCcw, danger: true },
      { label: "请求审核", action: "request-review", icon: Eye },
    ],
  });

  groups.push({
    title: "产物",
    items: [
      { label: "预览产物", action: "preview-artifact", icon: Eye },
      { label: "下载产物", action: "download-artifact", icon: Download },
      { label: "保存到工作区", action: "save-asset", icon: Save },
      { label: "查看生成历史", action: "view-history", icon: History },
      { label: "查看执行日志", action: "view-log", icon: FileText },
    ],
  });

  groups.push({
    title: "评估与修复",
    items: [
      { label: "资源估算", action: "estimate-resource", icon: Settings },
      { label: "质量评估", action: "quality-report", icon: Sparkles },
      { label: "自动修复", action: "auto-fix", icon: Wrench },
    ],
  });

  if (node?.nodeType === "剪辑" || node?.nodeType === "导出") {
    groups.push({
      title: "剪辑链路",
      items: [
        { label: "同步上游素材", action: "sync-upstream", icon: RefreshCw },
        { label: "创建 / 更新时间线", action: "create-timeline", icon: FilmIcon },
        { label: "智能体一键剪辑", action: "agent-clip", icon: Wand2 },
        { label: "渲染成片", action: "render", icon: VideoIcon },
        { label: "导出剪映草稿", action: "export-draft", icon: Download },
      ],
    });
  }

  groups.push({
    title: "数据",
    items: [
      { label: "导出节点 JSON", action: "export-node-json", icon: FileJson },
      { label: "从 JSON 导入", action: "import-node-json", icon: Upload },
      { label: "删除节点", action: "delete", icon: Trash2, danger: true, shortcut: "Del" },
    ],
  });

  return groups;
}

function MenuTitle({ children }: { children: ReactNode }) {
  return <div className="px-3 pb-1 pt-2 text-[11px] font-medium tracking-wide text-neutral-500">{children}</div>;
}

function MenuItem({
  children,
  onClick,
  danger = false,
  icon: Icon,
  shortcut,
}: {
  children: ReactNode;
  onClick: () => void;
  danger?: boolean;
  icon?: IconCmp;
  shortcut?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="menuitem"
      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-neutral-500 ${
        danger
          ? "text-red-300 hover:bg-red-500/10"
          : "text-neutral-200 hover:bg-neutral-800 hover:text-white"
      }`}
    >
      {Icon ? (
        <Icon size={14} className={`shrink-0 ${danger ? "text-red-300" : "text-neutral-400"}`} />
      ) : null}
      <span className="flex-1 truncate">{children}</span>
      {shortcut ? (
        <span className="shrink-0 text-[10px] text-neutral-600">{shortcut}</span>
      ) : null}
    </button>
  );
}

function MenuDivider() {
  return <div className="my-1 h-px bg-neutral-800" />;
}
