/**
 * 节流 Hook（零依赖）。
 *
 * 功能：
 * - useThrottle：值节流
 * - useThrottledCallback：函数节流
 * - 固定频率执行
 *
 * 用法：
 *   const throttledScroll = useThrottledCallback(onScroll, 100);
 *   const throttledValue = useThrottle(rapidValue, 200);
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** 值节流：固定频率更新值。 */
export function useThrottle<T>(value: T, intervalMs: number = 200): T {
  const [throttled, setThrottled] = useState(value);
  const lastRef = useRef(Date.now());
  const timerRef = useRef<number>(0);

  useEffect(() => {
    const now = Date.now();
    const remaining = intervalMs - (now - lastRef.current);

    if (remaining <= 0) {
      lastRef.current = now;
      setThrottled(value);
    } else {
      clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => {
        lastRef.current = Date.now();
        setThrottled(value);
      }, remaining);
    }

    return () => clearTimeout(timerRef.current);
  }, [value, intervalMs]);

  return throttled;
}

interface UseThrottledCallbackOptions {
  /** 间隔（ms） */
  intervalMs?: number;
  /** 前沿触发（默认 true） */
  leading?: boolean;
  /** 尾部触发（默认 true） */
  trailing?: boolean;
}

/** 函数节流。 */
export function useThrottledCallback<A extends any[]>(
  fn: (...args: A) => void,
  options: UseThrottledCallbackOptions | number = {},
): (...args: A) => void {
  const opts = typeof options === "number" ? { intervalMs: options } : options;
  const { intervalMs = 200, leading = true, trailing = true } = opts;

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const lastRef = useRef(0);
  const timerRef = useRef<number>(0);
  const argsRef = useRef<A | null>(null);

  const throttled = useCallback(
    (...args: A) => {
      const now = Date.now();
      const remaining = intervalMs - (now - lastRef.current);
      argsRef.current = args;

      if (remaining <= 0) {
        clearTimeout(timerRef.current);
        timerRef.current = 0;

        if (leading) {
          lastRef.current = now;
          fnRef.current(...args);
        }
      } else if (!timerRef.current && trailing) {
        timerRef.current = window.setTimeout(() => {
          lastRef.current = Date.now();
          timerRef.current = 0;
          if (argsRef.current) {
            fnRef.current(...argsRef.current);
          }
        }, remaining);
      }
    },
    [intervalMs, leading, trailing],
  );

  useEffect(() => {
    return () => clearTimeout(timerRef.current);
  }, []);

  return throttled;
}

export default useThrottle;
