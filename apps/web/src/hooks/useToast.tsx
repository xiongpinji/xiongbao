/**
 * 轻量 Toast 通知系统（零依赖）。
 *
 * 功能：
 * - useToast Hook：命令式调用
 * - 4 种类型：success / error / warning / info
 * - 自动消失（可配置时长）
 * - 堆叠显示（最多 5 条）
 * - 暗色主题 + 金色强调
 *
 * 用法：
 *   const toast = useToast();
 *   toast.success("保存成功");
 *   toast.error("操作失败", { duration: 5000 });
 */

import { useCallback, useRef, useState } from "react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration: number;
}

interface ToastOptions {
  duration?: number;
}

const ICONS: Record<ToastType, string> = {
  success: "✓",
  error: "✕",
  warning: "⚠",
  info: "ℹ",
};

const COLORS: Record<ToastType, string> = {
  success: "border-emerald-500/50 bg-emerald-950/80",
  error: "border-red-500/50 bg-red-950/80",
  warning: "border-amber-500/50 bg-amber-950/80",
  info: "border-sky-500/50 bg-sky-950/80",
};

const MAX_TOASTS = 5;
const DEFAULT_DURATION = 3000;

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (type: ToastType, message: string, opts?: ToastOptions) => {
      const id = Math.random().toString(36).slice(2, 10);
      const duration = opts?.duration ?? DEFAULT_DURATION;
      const toast: Toast = { id, type, message, duration };

      setToasts((prev) => [...prev.slice(-(MAX_TOASTS - 1)), toast]);

      const timer = setTimeout(() => remove(id), duration);
      timersRef.current.set(id, timer);
    },
    [remove],
  );

  const api = {
    success: (msg: string, opts?: ToastOptions) => push("success", msg, opts),
    error: (msg: string, opts?: ToastOptions) => push("error", msg, opts),
    warning: (msg: string, opts?: ToastOptions) => push("warning", msg, opts),
    info: (msg: string, opts?: ToastOptions) => push("info", msg, opts),
    remove,
  };

  return { toasts, ...api };
}

/** Toast 容器组件（放在 App 根节点） */
export function ToastContainer({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: string) => void }) {
  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[9999] flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-3 rounded-lg border px-4 py-3 shadow-xl backdrop-blur-sm ${COLORS[t.type]}`}
          style={{ animation: "slideIn 0.2s ease-out" }}
        >
          <span className="text-sm font-bold">{ICONS[t.type]}</span>
          <span className="text-sm text-neutral-200">{t.message}</span>
          <button
            onClick={() => onRemove(t.id)}
            className="ml-2 text-neutral-500 transition hover:text-neutral-300"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
