/**
 * 页面可见性 Hook（零依赖）。
 *
 * 功能：
 * - usePageVisibility：检测页面是否可见（标签切换/最小化）
 * - useIdle：用户空闲检测
 * - 可见性变化回调
 *
 * 用法：
 *   const isVisible = usePageVisibility();
 *   const isIdle = useIdle(5 * 60 * 1000); // 5分钟空闲
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** 页面可见性检测 */
export function usePageVisibility(
  onChange?: (visible: boolean) => void,
): boolean {
  const [isVisible, setIsVisible] = useState<boolean>(() => {
    if (typeof document === "undefined") return true;
    return !document.hidden;
  });

  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const handler = () => {
      const visible = !document.hidden;
      setIsVisible(visible);
      onChangeRef.current?.(visible);
    };

    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }, []);

  return isVisible;
}

// ─── 用户空闲检测 ───

interface UseIdleOptions {
  /** 空闲超时（ms） */
  timeout: number;
  /** 监听的事件（默认常见交互事件） */
  events?: string[];
  /** 是否在页面不可见时立即标记空闲 */
  idleOnHidden?: boolean;
}

const DEFAULT_EVENTS = [
  "mousemove",
  "mousedown",
  "keydown",
  "touchstart",
  "scroll",
  "wheel",
];

/** 用户空闲检测 */
export function useIdle(
  timeout: number,
  options: Omit<UseIdleOptions, "timeout"> = {},
): boolean {
  const { events = DEFAULT_EVENTS, idleOnHidden = true } = options;

  const [isIdle, setIsIdle] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isVisible = usePageVisibility();

  const resetTimer = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setIsIdle(false);
    timerRef.current = setTimeout(() => {
      setIsIdle(true);
    }, timeout);
  }, [timeout]);

  useEffect(() => {
    resetTimer();

    const handler = () => resetTimer();
    events.forEach((event) => {
      document.addEventListener(event, handler, { passive: true });
    });

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      events.forEach((event) => {
        document.removeEventListener(event, handler);
      });
    };
  }, [resetTimer, events]);

  // 页面隐藏时标记空闲
  useEffect(() => {
    if (idleOnHidden && !isVisible) {
      setIsIdle(true);
      if (timerRef.current) clearTimeout(timerRef.current);
    } else if (isVisible) {
      resetTimer();
    }
  }, [isVisible, idleOnHidden, resetTimer]);

  return isIdle;
}

export default usePageVisibility;
