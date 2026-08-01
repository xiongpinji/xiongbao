/**
 * 剪贴板操作 Hook（零依赖）。
 *
 * 功能：
 * - useClipboard：复制文本到剪贴板
 * - 支持成功/失败回调
 * - 自动重置 copied 状态
 * - 降级处理（旧浏览器）
 *
 * 用法：
 *   const { copy, copied, error } = useClipboard();
 *   <button onClick={() => copy("Hello")}>复制</button>
 *   {copied && <span>已复制!</span>}
 */

import { useCallback, useRef, useState } from "react";

interface UseClipboardOptions {
  /** copied 状态持续时间（ms，默认 2000） */
  timeout?: number;
  /** 成功回调 */
  onSuccess?: (text: string) => void;
  /** 失败回调 */
  onError?: (error: Error) => void;
}

interface UseClipboardReturn {
  /** 复制文本 */
  copy: (text: string) => Promise<void>;
  /** 是否刚复制成功 */
  copied: boolean;
  /** 错误信息 */
  error: Error | null;
}

export function useClipboard(options: UseClipboardOptions = {}): UseClipboardReturn {
  const { timeout = 2000, onSuccess, onError } = options;
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = useCallback(
    async (text: string) => {
      setError(null);

      try {
        // 优先使用 Clipboard API
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else {
          // 降级：textarea + execCommand
          const textarea = document.createElement("textarea");
          textarea.value = text;
          textarea.style.position = "fixed";
          textarea.style.left = "-9999px";
          textarea.style.top = "-9999px";
          document.body.appendChild(textarea);
          textarea.focus();
          textarea.select();

          const success = document.execCommand("copy");
          document.body.removeChild(textarea);

          if (!success) {
            throw new Error("execCommand copy failed");
          }
        }

        setCopied(true);
        onSuccess?.(text);

        // 自动重置
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setCopied(false), timeout);
      } catch (e) {
        const err = e instanceof Error ? e : new Error("Copy failed");
        setError(err);
        setCopied(false);
        onError?.(err);
      }
    },
    [timeout, onSuccess, onError],
  );

  return { copy, copied, error };
}

export default useClipboard;
