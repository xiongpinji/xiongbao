/**
 * 数据轮询 Hook（零依赖）。
 *
 * 功能：
 * - usePolling：定时轮询异步数据
 * - 支持暂停 / 恢复 / 立即刷新
 * - 错误重试 + 指数退避
 * - 页面不可见时自动暂停
 *
 * 用法：
 *   const { data, error, isLoading, refresh, pause, resume } = usePolling(
 *     () => fetch("/api/status").then(r => r.json()),
 *     { interval: 5000 },
 *   );
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UsePollingOptions {
  /** 轮询间隔（ms，默认 5000） */
  interval?: number;
  /** 是否立即执行（默认 true） */
  immediate?: boolean;
  /** 是否启用（默认 true） */
  enabled?: boolean;
  /** 错误时最大重试次数（默认 3） */
  maxRetries?: number;
  /** 页面不可见时是否暂停（默认 true） */
  pauseOnHidden?: boolean;
  /** 成功回调 */
  onSuccess?: (data: any) => void;
  /** 错误回调 */
  onError?: (error: Error) => void;
}

interface UsePollingReturn<T> {
  /** 最新数据 */
  data: T | null;
  /** 错误信息 */
  error: Error | null;
  /** 是否正在加载 */
  isLoading: boolean;
  /** 是否暂停 */
  isPaused: boolean;
  /** 立即刷新 */
  refresh: () => void;
  /** 暂停轮询 */
  pause: () => void;
  /** 恢复轮询 */
  resume: () => void;
}

export function usePolling<T>(
  fn: () => Promise<T>,
  options: UsePollingOptions = {},
): UsePollingReturn<T> {
  const {
    interval = 5000,
    immediate = true,
    enabled = true,
    maxRetries = 3,
    pauseOnHidden = true,
    onSuccess,
    onError,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const mountedRef = useRef(true);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const execute = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await fnRef.current();
      if (!mountedRef.current) return;
      setData(result);
      setError(null);
      retryCountRef.current = 0;
      onSuccess?.(result);
    } catch (e) {
      if (!mountedRef.current) return;
      const err = e instanceof Error ? e : new Error("Polling failed");
      setError(err);
      onError?.(err);
      retryCountRef.current += 1;
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, [onSuccess, onError]);

  const scheduleNext = useCallback(() => {
    clearTimer();
    // 错误时使用指数退避
    const backoff =
      retryCountRef.current > 0
        ? Math.min(interval * Math.pow(2, retryCountRef.current), 60000)
        : interval;

    // 超过最大重试次数停止
    if (retryCountRef.current > maxRetries) return;

    timerRef.current = setTimeout(async () => {
      await execute();
      scheduleNext();
    }, backoff);
  }, [interval, maxRetries, execute, clearTimer]);

  const refresh = useCallback(() => {
    retryCountRef.current = 0;
    clearTimer();
    execute().then(scheduleNext);
  }, [execute, scheduleNext, clearTimer]);

  const pause = useCallback(() => {
    setIsPaused(true);
    clearTimer();
  }, [clearTimer]);

  const resume = useCallback(() => {
    setIsPaused(false);
    retryCountRef.current = 0;
    scheduleNext();
  }, [scheduleNext]);

  // 主轮询逻辑
  useEffect(() => {
    mountedRef.current = true;

    if (!enabled || isPaused) return;

    if (immediate) {
      execute().then(scheduleNext);
    } else {
      scheduleNext();
    }

    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [enabled, isPaused, immediate, execute, scheduleNext, clearTimer]);

  // 页面可见性监听
  useEffect(() => {
    if (!pauseOnHidden) return;

    const handleVisibility = () => {
      if (document.hidden) {
        clearTimer();
      } else if (enabled && !isPaused) {
        retryCountRef.current = 0;
        scheduleNext();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [pauseOnHidden, enabled, isPaused, clearTimer, scheduleNext]);

  return { data, error, isLoading, isPaused, refresh, pause, resume };
}

export default usePolling;
