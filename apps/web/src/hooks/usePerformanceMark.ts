/**
 * 性能标记 Hook（零依赖）。
 *
 * 功能：
 * - usePerformanceMark：组件渲染性能追踪
 * - useMeasure：测量代码块执行耗时
 * - Performance API 封装
 *
 * 用法：
 *   usePerformanceMark("AgentPanel");
 *   const measure = useMeasure();
 *   measure.start("fetch-agents");
 *   await fetchAgents();
 *   measure.end("fetch-agents"); // → 输出耗时
 */

import { useCallback, useEffect, useRef } from "react";

/** 组件渲染性能标记 */
export function usePerformanceMark(name: string, enabled: boolean = true): void {
  const renderCount = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    if (typeof performance === "undefined") return;

    renderCount.current += 1;
    const markName = `${name}:render:${renderCount.current}`;

    performance.mark(markName);

    // 首次渲染标记
    if (renderCount.current === 1) {
      performance.mark(`${name}:mounted`);
    }

    return () => {
      // 组件卸载时测量生命周期
      if (renderCount.current === 1) {
        try {
          performance.measure(`${name}:mount-time`, `${name}:mounted`);
        } catch {
          // 忽略
        }
      }
    };
  });
}

interface MeasureEntry {
  name: string;
  duration: number;
  startTime: number;
}

interface UseMeasureReturn {
  /** 开始计时 */
  start: (name: string) => void;
  /** 结束计时，返回耗时（ms） */
  end: (name: string) => number | null;
  /** 获取所有记录 */
  entries: () => MeasureEntry[];
  /** 清除所有记录 */
  clear: () => void;
}

/** 代码块执行耗时测量 */
export function useMeasure(): UseMeasureReturn {
  const startsRef = useRef<Map<string, number>>(new Map());
  const entriesRef = useRef<MeasureEntry[]>([]);

  const start = useCallback((name: string) => {
    startsRef.current.set(name, performance.now());
  }, []);

  const end = useCallback((name: string): number | null => {
    const startTime = startsRef.current.get(name);
    if (startTime === undefined) return null;

    const duration = performance.now() - startTime;
    startsRef.current.delete(name);

    entriesRef.current.push({ name, duration, startTime });

    // 同时写入 Performance API
    if (typeof performance !== "undefined" && performance.mark) {
      try {
        performance.mark(`${name}:end`);
        performance.measure(name, { start: startTime, end: performance.now() });
      } catch {
        // 忽略
      }
    }

    return Math.round(duration * 100) / 100;
  }, []);

  const entries = useCallback(() => [...entriesRef.current], []);

  const clear = useCallback(() => {
    startsRef.current.clear();
    entriesRef.current = [];
  }, []);

  return { start, end, entries, clear };
}

/** 测量异步函数耗时（非 Hook，工具函数） */
export async function measureAsync<T>(
  name: string,
  fn: () => Promise<T>,
): Promise<{ result: T; duration: number }> {
  const startTime = performance.now();
  const result = await fn();
  const duration = performance.now() - startTime;

  if (typeof performance !== "undefined" && performance.mark) {
    try {
      performance.measure(`async:${name}`, { start: startTime, end: performance.now() });
    } catch {
      // 忽略
    }
  }

  return { result, duration: Math.round(duration * 100) / 100 };
}

export default usePerformanceMark;
