/**
 * 空闲检测 Hook（零依赖）。
 *
 * 功能：
 * - useIdle：检测用户不活动
 * - 可配置超时
 * - 活跃/空闲回调
 *
 * 用法：
 *   const isIdle = useIdle(5 * 60 * 1000); // 5分钟无操作
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseIdleOptions {
  /** 空闲回调 */
  onIdle?: () => void;
  /** 活跃回调 */
  onActive?: () => void;
  /** 监听事件 */
  events?: string[];
  /** 是否初始为空闲 */
  initialState?: boolean;
}

const DEFAULT_EVENTS = ["mousemove", "keydown", "scroll", "touchstart", "click"];

export function useIdle(
  timeoutMs: number = 60000,
  options: UseIdleOptions = {},
): boolean {
  const { onIdle, onActive, events = DEFAULT_EVENTS, initialState = false } = options;

  const [isIdle, setIsIdle] = useState(initialState);
  const timerRef = useRef<number>(0);
  const callbacksRef = useRef({ onIdle, onActive });
  callbacksRef.current = { onIdle, onActive };

  const handleActivity = useCallback(() => {
    // 从空闲恢复
    setIsIdle((prev) => {
      if (prev) {
        callbacksRef.current.onActive?.();
      }
      return false;
    });

    // 重置计时器
    clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      setIsIdle(true);
      callbacksRef.current.onIdle?.();
    }, timeoutMs);
  }, [timeoutMs]);

  useEffect(() => {
    // 初始计时
    timerRef.current = window.setTimeout(() => {
      setIsIdle(true);
      callbacksRef.current.onIdle?.();
    }, timeoutMs);

    for (const event of events) {
      document.addEventListener(event, handleActivity, { passive: true });
    }

    return () => {
      clearTimeout(timerRef.current);
      for (const event of events) {
        document.removeEventListener(event, handleActivity);
      }
    };
  }, [timeoutMs, events, handleActivity]);

  return isIdle;
}

export default useIdle;
