/**
 * 剪贴板操作 Hook（零依赖）。
 *
 * 功能：
 * - useClipboard：复制文本到剪贴板
 * - 复制状态反馈（成功/失败/超时重置）
 * - 兼容 Clipboard API + execCommand 降级
 *
 * 用法：
 *   const { copy, copied, error } = useClipboard({ timeout: 2000 });
 *   <button onClick={() => copy("Hello!")}>{copied ? "已复制" : "复制"}</button>
 */

import { useCallback, useRef, useState } from "react";

interface UseClipboardOptions {
  /** 复制成功后状态保持时间（ms，默认 2000） */
  timeout?: number;
  /** 复制成功回调 */
  onSuccess?: (text: string) => void;
  /** 复制失败回调 */
  onError?: (error: Error) => void;
}

interface UseClipboardReturn {
  /** 复制文本 */
  copy: (text: string) => Promise<void>;
  /** 是否刚复制成功 */
  copied: boolean;
  /** 最近一次错误 */
  error: Error | null;
  /** 是否支持 Clipboard API */
  isSupported: boolean;
}

/** 降级复制（execCommand） */
function fallbackCopy(text: string): void {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

export function useClipboard(options: UseClipboardOptions = {}): UseClipboardReturn {
  const { timeout = 2000, onSuccess, onError } = options;

  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isSupported =
    typeof navigator !== "undefined" && !!navigator.clipboard;

  const copy = useCallback(
    async (text: string) => {
      // 清除之前的计时器
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      try {
        if (isSupported) {
          await navigator.clipboard.writeText(text);
        } else {
          fallbackCopy(text);
        }

        setCopied(true);
        setError(null);
        onSuccess?.(text);

        // 超时重置
        timerRef.current = setTimeout(() => {
          setCopied(false);
          timerRef.current = null;
        }, timeout);
      } catch (err) {
        const copyError =
          err instanceof Error ? err : new Error("Clipboard write failed");
        setCopied(false);
        setError(copyError);
        onError?.(copyError);
      }
    },
    [isSupported, timeout, onSuccess, onError],
  );

  return { copy, copied, error, isSupported };
}

export default useClipboard;
