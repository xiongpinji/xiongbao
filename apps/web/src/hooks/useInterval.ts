/**
 * 定时器 Hook（零依赖）。
 *
 * 功能：
 * - useInterval：声明式 setInterval
 * - useTimeout：声明式 setTimeout
 * - 动态延迟 / 暂停
 *
 * 用法：
 *   useInterval(() => setCount(c => c + 1), 1000);
 *   useTimeout(() => setShow(false), 5000);
 */

import { useEffect, useRef } from "react";

/** 声明式 setInterval。传 null 暂停。 */
export function useInterval(callback: () => void, delayMs: number | null): void {
  const savedRef = useRef(callback);
  savedRef.current = callback;

  useEffect(() => {
    if (delayMs === null) return;

    const id = setInterval(() => savedRef.current(), delayMs);
    return () => clearInterval(id);
  }, [delayMs]);
}

/** 声明式 setTimeout。传 null 取消。 */
export function useTimeout(callback: () => void, delayMs: number | null): void {
  const savedRef = useRef(callback);
  savedRef.current = callback;

  useEffect(() => {
    if (delayMs === null) return;

    const id = setTimeout(() => savedRef.current(), delayMs);
    return () => clearTimeout(id);
  }, [delayMs]);
}

/** 可暂停的 interval，返回控制方法。 */
export function usePausableInterval(
  callback: () => void,
  delayMs: number,
  initialPaused: boolean = false,
): { isPaused: boolean; pause: () => void; resume: () => void } {
  const savedRef = useRef(callback);
  savedRef.current = callback;
  const pausedRef = useRef(initialPaused);
  const [, forceUpdate] = useForceUpdate();

  useEffect(() => {
    const id = setInterval(() => {
      if (!pausedRef.current) {
        savedRef.current();
      }
    }, delayMs);
    return () => clearInterval(id);
  }, [delayMs]);

  const pause = () => { pausedRef.current = true; forceUpdate(); };
  const resume = () => { pausedRef.current = false; forceUpdate(); };

  return { isPaused: pausedRef.current, pause, resume };
}

// 内部辅助
import { useState, useCallback } from "react";
function useForceUpdate(): [number, () => void] {
  const [n, setN] = useState(0);
  const update = useCallback(() => setN((v) => v + 1), []);
  return [n, update];
}

export default useInterval;
