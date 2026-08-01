/**
 * 剪贴板 Hook（零依赖）。
 *
 * 功能：
 * - useClipboard：复制文本到剪贴板
 * - 复制状态反馈
 * - 读取剪贴板内容
 * - 降级方案（execCommand）
 *
 * 用法：
 *   const { copy, copied, error } = useClipboard();
 *   <button onClick={() => copy("Hello")}>复制</button>
 */

import { useCallback, useRef, useState } from "react";

interface UseClipboardOptions {
  /** 复制成功状态持续时间（ms，默认 2000） */
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
  /** 错误信息 */
  error: Error | null;
  /** 读取剪贴板 */
  read: () => Promise<string>;
  /** 是否支持 */
  isSupported: boolean;
}

export function useClipboard(options: UseClipboardOptions = {}): UseClipboardReturn {
  const { timeout = 2000, onSuccess, onError } = options;

  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const timerRef = useRef<number>(0);
  const callbacksRef = useRef({ onSuccess, onError });
  callbacksRef.current = { onSuccess, onError };

  const isSupported = typeof navigator !== "undefined" && !!navigator.clipboard;

  const fallbackCopy = useCallback((text: string): boolean => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      return document.execCommand("copy");
    } catch {
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  }, []);

  const copy = useCallback(
    async (text: string) => {
      clearTimeout(timerRef.current);
      setError(null);

      try {
        if (isSupported) {
          await navigator.clipboard.writeText(text);
        } else {
          const ok = fallbackCopy(text);
          if (!ok) throw new Error("Fallback copy failed");
        }

        setCopied(true);
        callbacksRef.current.onSuccess?.(text);
        timerRef.current = window.setTimeout(() => setCopied(false), timeout);
      } catch (e) {
        const err = e instanceof Error ? e : new Error(String(e));
        setError(err);
        setCopied(false);
        callbacksRef.current.onError?.(err);
      }
    },
    [isSupported, fallbackCopy, timeout],
  );

  const read = useCallback(async (): Promise<string> => {
    if (!isSupported) throw new Error("Clipboard API not supported");
    return navigator.clipboard.readText();
  }, [isSupported]);

  return { copy, copied, error, read, isSupported };
}

export default useClipboard;
