/**
 * 防抖 Hook（零依赖）。
 *
 * 功能：
 * - useDebounce：值防抖
 * - useDebouncedCallback：函数防抖
 * - 支持 leading/trailing
 *
 * 用法：
 *   const debouncedValue = useDebounce(searchText, 300);
 *   const debouncedSearch = useDebouncedCallback(search, 500);
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** 值防抖：延迟更新值。 */
export function useDebounce<T>(value: T, delayMs: number = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

interface UseDebouncedCallbackOptions {
  /** 延迟（ms） */
  delayMs?: number;
  /** 前沿触发 */
  leading?: boolean;
  /** 尾部触发（默认 true） */
  trailing?: boolean;
}

/** 函数防抖。 */
export function useDebouncedCallback<A extends any[]>(
  fn: (...args: A) => void,
  options: UseDebouncedCallbackOptions | number = {},
): ((...args: A) => void) & { cancel: () => void; flush: () => void } {
  const opts = typeof options === "number" ? { delayMs: options } : options;
  const { delayMs = 300, leading = false, trailing = true } = opts;

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const timerRef = useRef<number>(0);
  const argsRef = useRef<A | null>(null);
  const leadingCalledRef = useRef(false);

  const cancel = useCallback(() => {
    clearTimeout(timerRef.current);
    timerRef.current = 0;
    argsRef.current = null;
    leadingCalledRef.current = false;
  }, []);

  const flush = useCallback(() => {
    if (argsRef.current && trailing) {
      fnRef.current(...argsRef.current);
    }
    cancel();
  }, [trailing, cancel]);

  const debounced = useCallback(
    (...args: A) => {
      argsRef.current = args;
      clearTimeout(timerRef.current);

      // leading edge
      if (leading && !leadingCalledRef.current) {
        leadingCalledRef.current = true;
        fnRef.current(...args);
      }

      timerRef.current = window.setTimeout(() => {
        if (trailing && !(leading && leadingCalledRef.current)) {
          fnRef.current(...(argsRef.current || args));
        }
        leadingCalledRef.current = false;
        argsRef.current = null;
      }, delayMs);
    },
    [delayMs, leading, trailing],
  ) as ((...args: A) => void) & { cancel: () => void; flush: () => void };

  debounced.cancel = cancel;
  debounced.flush = flush;

  useEffect(() => cancel, [cancel]);

  return debounced;
}

export default useDebounce;
