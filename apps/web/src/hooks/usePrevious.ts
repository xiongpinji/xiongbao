/**
 * 前一值 Hook（零依赖）。
 *
 * 功能：
 * - usePrevious：获取上一次渲染的值
 * - useDelta：获取值变化量
 * - useHistory：保留最近 N 次值
 *
 * 用法：
 *   const prevCount = usePrevious(count);
 *   const delta = useDelta(count);
 */

import { useEffect, useRef, useState } from "react";

/** 获取前一次的值。 */
export function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T | undefined>(undefined);

  useEffect(() => {
    ref.current = value;
  }, [value]);

  return ref.current;
}

/** 获取值变化量（数字）。 */
export function useDelta(value: number): number {
  const prev = usePrevious(value);
  return prev === undefined ? 0 : value - prev;
}

/** 保留最近 N 次值历史。 */
export function useHistory<T>(value: T, maxSize: number = 10): T[] {
  const [history, setHistory] = useState<T[]>([value]);
  const prevRef = useRef(value);

  useEffect(() => {
    if (prevRef.current !== value) {
      prevRef.current = value;
      setHistory((prev) => {
        const next = [...prev, value];
        return next.length > maxSize ? next.slice(-maxSize) : next;
      });
    }
  }, [value, maxSize]);

  return history;
}

/** 值是否变化。 */
export function useChanged(value: any): boolean {
  const prev = usePrevious(value);
  return prev !== undefined && prev !== value;
}

export default usePrevious;
