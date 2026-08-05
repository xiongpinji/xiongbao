/**
 * 错误重试 Hook（零依赖）。
 *
 * 功能：
 * - useRetry：异步操作失败自动重试
 * - 指数退避 + 随机抖动
 * - 可配置最大重试次数
 * - 手动重试 / 重置
 *
 * 用法：
 *   const { execute, isLoading, error, retryCount, reset } = useRetry(
 *     () => fetchData(),
 *     { maxRetries: 3, baseDelay: 1000 },
 *   );
 *   useEffect(() => { execute(); }, []);
 */

import { useCallback, useRef, useState } from "react";

interface UseRetryOptions {
  /** 最大重试次数（默认 3） */
  maxRetries?: number;
  /** 基础延迟（ms，默认 1000） */
  baseDelay?: number;
  /** 最大延迟（ms，默认 30000） */
  maxDelay?: number;
  /** 是否添加随机抖动（默认 true） */
  jitter?: boolean;
  /** 重试条件（返回 false 则不重试） */
  shouldRetry?: (error: Error, attempt: number) => boolean;
  /** 重试回调 */
  onRetry?: (error: Error, attempt: number) => void;
  /** 成功回调 */
  onSuccess?: (data: any) => void;
  /** 最终失败回调 */
  onError?: (error: Error) => void;
}

interface UseRetryReturn<T> {
  /** 执行（含重试） */
  execute: (...args: any[]) => Promise<T | undefined>;
  /** 是否加载中 */
  isLoading: boolean;
  /** 最新错误 */
  error: Error | null;
  /** 当前重试次数 */
  retryCount: number;
  /** 是否正在重试 */
  isRetrying: boolean;
  /** 重置状态 */
  reset: () => void;
}

/** 计算退避延迟 */
function getDelay(
  attempt: number,
  baseDelay: number,
  maxDelay: number,
  jitter: boolean,
): number {
  const exponential = baseDelay * Math.pow(2, attempt);
  const capped = Math.min(exponential, maxDelay);

  if (!jitter) return capped;

  // Full jitter: random between 0 and capped
  return Math.random() * capped;
}

/** 等待指定毫秒 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function useRetry<T>(
  fn: (...args: any[]) => Promise<T>,
  options: UseRetryOptions = {},
): UseRetryReturn<T> {
  const {
    maxRetries = 3,
    baseDelay = 1000,
    maxDelay = 30000,
    jitter = true,
    shouldRetry,
    onRetry,
    onSuccess,
    onError,
  } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const mountedRef = useRef(true);

  const execute = useCallback(
    async (...args: any[]): Promise<T | undefined> => {
      setIsLoading(true);
      setError(null);
      setRetryCount(0);
      setIsRetrying(false);

      let lastError: Error | null = null;

      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          const result = await fnRef.current(...args);
          if (mountedRef.current) {
            setIsLoading(false);
            setIsRetrying(false);
            onSuccess?.(result);
          }
          return result;
        } catch (e) {
          lastError = e instanceof Error ? e : new Error(String(e));

          if (!mountedRef.current) return undefined;

          // 检查是否应该重试
          if (attempt >= maxRetries) break;
          if (shouldRetry && !shouldRetry(lastError, attempt)) break;

          // 等待退避
          setRetryCount(attempt + 1);
          setIsRetrying(true);
          onRetry?.(lastError, attempt + 1);

          const delay = getDelay(attempt, baseDelay, maxDelay, jitter);
          await sleep(delay);
        }
      }

      // 全部失败
      if (mountedRef.current) {
        setError(lastError);
        setIsLoading(false);
        setIsRetrying(false);
        onError?.(lastError!);
      }

      return undefined;
    },
    [maxRetries, baseDelay, maxDelay, jitter, shouldRetry, onRetry, onSuccess, onError],
  );

  const reset = useCallback(() => {
    setIsLoading(false);
    setError(null);
    setRetryCount(0);
    setIsRetrying(false);
  }, []);

  return { execute, isLoading, error, retryCount, isRetrying, reset };
}

export default useRetry;
