/**
 * Web Worker Hook（零依赖）。
 *
 * 功能：
 * - useWorker：在 Web Worker 中执行耗时计算
 * - 自动创建/销毁 Worker
 * - 消息传递 + 错误处理
 * - 支持 Inline Worker（Blob URL）
 *
 * 用法：
 *   const { post, result, isLoading, error } = useWorker(workerFn);
 *   post({ numbers: [1, 2, 3] });
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseWorkerReturn<TInput, TOutput> {
  /** 发送消息到 Worker */
  post: (data: TInput) => void;
  /** 最近一次结果 */
  result: TOutput | null;
  /** 是否处理中 */
  isLoading: boolean;
  /** 错误信息 */
  error: Error | null;
  /** 终止 Worker */
  terminate: () => void;
}

/**
 * 创建 Inline Worker。
 * @param fn Worker 内执行的函数（接收 message event）
 */
export function useWorker<TInput = any, TOutput = any>(
  fn: (e: MessageEvent<TInput>) => void,
): UseWorkerReturn<TInput, TOutput> {
  const [result, setResult] = useState<TOutput | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  // 创建 Worker
  useEffect(() => {
    const blob = new Blob(
      [`self.onmessage = ${fnRef.current.toString()}`],
      { type: "application/javascript" },
    );
    const url = URL.createObjectURL(blob);
    const worker = new Worker(url);

    worker.onmessage = (e: MessageEvent<TOutput>) => {
      setResult(e.data);
      setIsLoading(false);
    };

    worker.onerror = (e) => {
      setError(new Error(e.message || "Worker error"));
      setIsLoading(false);
    };

    workerRef.current = worker;

    return () => {
      worker.terminate();
      URL.revokeObjectURL(url);
      workerRef.current = null;
    };
  }, []);

  const post = useCallback((data: TInput) => {
    if (!workerRef.current) return;
    setIsLoading(true);
    setError(null);
    workerRef.current.postMessage(data);
  }, []);

  const terminate = useCallback(() => {
    workerRef.current?.terminate();
    workerRef.current = null;
    setIsLoading(false);
  }, []);

  return { post, result, isLoading, error, terminate };
}

export default useWorker;
