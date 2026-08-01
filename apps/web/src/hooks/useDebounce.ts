/**
 * 防抖 / 节流 Hooks（零依赖）。
 *
 * - useDebounce：延迟执行（搜索输入）
 * - useThrottle：固定频率执行（滚动事件）
 * - useDebouncedValue：值防抖
 *
 * 用法：
 *   const debouncedSearch = useDebounce(searchFn, 300);
 *   const throttledScroll = useThrottle(onScroll, 100);
 *   const debouncedQuery = useDebouncedValue(query, 500);
 */

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 防抖函数：延迟 ms 后执行，期间重复调用重置计时。
 */
export function useDebounce<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 300,
): (...args: Parameters<T>) => void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return useCallback(
    (...args: Parameters<T>) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        fnRef.current(...args);
      }, delay);
    },
    [delay],
  );
}

/**
 * 节流函数：每 ms 毫秒最多执行一次。
 */
export function useThrottle<T extends (...args: any[]) => any>(
  fn: T,
  interval: number = 100,
): (...args: Parameters<T>) => void {
  const lastRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return useCallback(
    (...args: Parameters<T>) => {
      const now = Date.now();
      const remaining = interval - (now - lastRef.current);

      if (remaining <= 0) {
        lastRef.current = now;
        fnRef.current(...args);
      } else if (!timerRef.current) {
        timerRef.current = setTimeout(() => {
          lastRef.current = Date.now();
          timerRef.current = null;
          fnRef.current(...args);
        }, remaining);
      }
    },
    [interval],
  );
}

/**
 * 值防抖：返回延迟更新后的值。
 */
export function useDebouncedValue<T>(value: T, delay: number = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
