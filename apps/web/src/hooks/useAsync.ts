/**
 * 异步操作 Hook（零依赖）。
 *
 * 功能：
 * - useAsync：管理异步函数状态
 * - loading/error/data 三态
 * - 自动/手动执行
 * - 竞态取消
 *
 * 用法：
 *   const { data, loading, error, execute } = useAsync(fetchUser, { immediate: true });
 */

import { useCallback, useEffect, useRef, useState } from "react";

type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: Error | null;
};

interface UseAsyncOptions {
  /** 是否立即执行（默认 true） */
  immediate?: boolean;
  /** 成功回调 */
  onSuccess?: (data: any) => void;
  /** 失败回调 */
  onError?: (error: Error) => void;
}

interface UseAsyncReturn<T, A extends any[]> extends AsyncState<T> {
  /** 手动执行 */
  execute: (...args: A) => Promise<T | null>;
  /** 重置状态 */
  reset: () => void;
}

export function useAsync<T, A extends any[] = []>(
  fn: (...args: A) => Promise<T>,
  options: UseAsyncOptions = {},
): UseAsyncReturn<T, A> {
  const { immediate = true, onSuccess, onError } = options;

  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: immediate,
    error: null,
  });

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const callbacksRef = useRef({ onSuccess, onError });
  callbacksRef.current = { onSuccess, onError };
  const callIdRef = useRef(0);

  const execute = useCallback(async (...args: A): Promise<T | null> => {
    const callId = ++callIdRef.current;
    setState((prev) => ({ ...prev, loading: true, error: null }));

    try {
      const result = await fnRef.current(...args);

      // 竞态检查
      if (callId !== callIdRef.current) return null;

      setState({ data: result, loading: false, error: null });
      callbacksRef.current.onSuccess?.(result);
      return result;
    } catch (e) {
      if (callId !== callIdRef.current) return null;

      const error = e instanceof Error ? e : new Error(String(e));
      setState((prev) => ({ ...prev, loading: false, error }));
      callbacksRef.current.onError?.(error);
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    callIdRef.current++;
    setState({ data: null, loading: false, error: null });
  }, []);

  useEffect(() => {
    if (immediate) {
      execute(...([] as unknown as A));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...state, execute, reset };
}

export default useAsync;
