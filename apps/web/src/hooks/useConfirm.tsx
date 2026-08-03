/**
 * 确认对话框 Hook（Promise 化）。
 *
 * 功能：
 * - useConfirm：命令式调用，返回 Promise<boolean>
 * - 支持自定义标题/内容/按钮文案
 * - 危险操作红色确认按钮
 * - 暗色主题模态框
 *
 * 用法：
 *   const { confirm, ConfirmDialog } = useConfirm();
 *   const ok = await confirm({ title: "删除", message: "确定删除？", danger: true });
 *   if (ok) doDelete();
 *   // 在 JSX 中: <ConfirmDialog />
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}

interface ConfirmState extends ConfirmOptions {
  open: boolean;
  resolve: ((value: boolean) => void) | null;
}

const DEFAULT_STATE: ConfirmState = {
  open: false,
  message: "",
  resolve: null,
};

export function useConfirm() {
  const [state, setState] = useState<ConfirmState>(DEFAULT_STATE);

  const confirm = useCallback((opts: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({ ...opts, open: true, resolve });
    });
  }, []);

  const handleClose = useCallback((result: boolean) => {
    setState((prev) => {
      prev.resolve?.(result);
      return DEFAULT_STATE;
    });
  }, []);

  const ConfirmDialog = useCallback(() => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const confirmBtnRef = useRef<HTMLButtonElement>(null);
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const cancelBtnRef = useRef<HTMLButtonElement>(null);

    // eslint-disable-next-line react-hooks/rules-of-hooks
    useEffect(() => {
      if (!state.open) return;
      // 记录打开前聚焦的元素，关闭时归还焦点，避免键盘用户焦点丢失（落到 body）
      const previouslyFocused = document.activeElement as HTMLElement | null;
      confirmBtnRef.current?.focus();
      const handler = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          handleClose(false);
          return;
        }
        // 焦点陷阱：Tab 在取消/确认两按钮间循环，防止逃出模态框
        if (e.key === "Tab") {
          const focusables = [cancelBtnRef.current, confirmBtnRef.current].filter(
            (el): el is HTMLButtonElement => el !== null
          );
          if (focusables.length === 0) return;
          const first = focusables[0];
          const last = focusables[focusables.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      };
      window.addEventListener("keydown", handler);
      return () => {
        window.removeEventListener("keydown", handler);
        previouslyFocused?.focus?.();
      };
    }, [state.open, handleClose]);

    if (!state.open) return null;

    return (
      <div className="fixed inset-0 z-[9998] flex items-center justify-center">
        {/* 遮罩 */}
        <div
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          onClick={() => handleClose(false)}
        />

        {/* 对话框 */}
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
          aria-describedby="confirm-dialog-message"
          className="xb-fade-up relative w-full max-w-sm rounded-lg border border-neutral-700 bg-neutral-900 p-6 shadow-xl shadow-black/30"
        >
          {state.title && (
            <h3 id="confirm-dialog-title" className="mb-2 text-base font-semibold text-neutral-100">
              {state.title}
            </h3>
          )}
          <p id="confirm-dialog-message" className="mb-6 text-sm text-neutral-400">{state.message}</p>

          <div className="flex justify-end gap-3">
            <button
              ref={cancelBtnRef}
              onClick={() => handleClose(false)}
              className="rounded-lg border border-neutral-600 px-4 py-2 text-sm text-neutral-300 transition hover:bg-neutral-800"
            >
              {state.cancelText || "取消"}
            </button>
            <button
              ref={confirmBtnRef}
              onClick={() => handleClose(true)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                state.danger
                  ? "bg-red-600 text-white hover:bg-red-500"
                  : "bg-neutral-100 text-black hover:bg-white"
              }`}
            >
              {state.confirmText || "确认"}
            </button>
          </div>
        </div>
      </div>
    );
  }, [state, handleClose]);

  return { confirm, ConfirmDialog };
}
