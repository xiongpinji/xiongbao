/**
 * 离线队列 Hook（零依赖）。
 *
 * 功能：
 * - useOfflineQueue：离线时缓存操作，恢复后自动重放
 * - 队列持久化（localStorage）
 * - 重试策略 + 最大重试
 * - 队列状态监控
 *
 * 用法：
 *   const { enqueue, queue, flush, isOnline } = useOfflineQueue({
 *     processor: async (item) => api.sync(item),
 *     storageKey: "offline_actions",
 *   });
 *   enqueue({ type: "create_note", payload: note });
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface QueueItem<T = any> {
  id: string;
  data: T;
  enqueuedAt: number;
  retries: number;
}

interface UseOfflineQueueOptions<T = any> {
  /** 处理函数（在线时执行） */
  processor: (item: T) => Promise<void>;
  /** localStorage 键名（默认 "offline_queue"） */
  storageKey?: string;
  /** 最大重试次数（默认 3） */
  maxRetries?: number;
  /** 是否自动 flush（默认 true） */
  autoFlush?: boolean;
}

interface UseOfflineQueueReturn<T = any> {
  /** 加入队列 */
  enqueue: (data: T) => void;
  /** 当前队列 */
  queue: QueueItem<T>[];
  /** 手动 flush */
  flush: () => Promise<void>;
  /** 清空队列 */
  clear: () => void;
  /** 是否在线 */
  isOnline: boolean;
  /** 是否正在处理 */
  isProcessing: boolean;
  /** 队列大小 */
  size: number;
}

let queueIdCounter = 0;

export function useOfflineQueue<T = any>(
  options: UseOfflineQueueOptions<T>,
): UseOfflineQueueReturn<T> {
  const {
    processor,
    storageKey = "offline_queue",
    maxRetries = 3,
    autoFlush = true,
  } = options;

  const [queue, setQueue] = useState<QueueItem<T>[]>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== "undefined" ? navigator.onLine : true,
  );
  const [isProcessing, setIsProcessing] = useState(false);

  const processorRef = useRef(processor);
  processorRef.current = processor;
  const queueRef = useRef(queue);
  queueRef.current = queue;

  // 持久化
  const persist = useCallback(
    (items: QueueItem<T>[]) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(items));
      } catch {
        // 存储满等异常
      }
    },
    [storageKey],
  );

  // 在线状态监听
  useEffect(() => {
    const goOnline = () => {
      setIsOnline(true);
      if (autoFlush) flushRef.current();
    };
    const goOffline = () => setIsOnline(false);

    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [autoFlush]);

  const enqueue = useCallback(
    (data: T) => {
      const item: QueueItem<T> = {
        id: `oq_${++queueIdCounter}_${Date.now()}`,
        data,
        enqueuedAt: Date.now(),
        retries: 0,
      };
      setQueue((prev) => {
        const next = [...prev, item];
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const flush = useCallback(async () => {
    if (isProcessing || !navigator.onLine) return;
    setIsProcessing(true);

    const items = [...queueRef.current];
    const failed: QueueItem<T>[] = [];

    for (const item of items) {
      try {
        await processorRef.current(item.data);
      } catch {
        if (item.retries < maxRetries) {
          failed.push({ ...item, retries: item.retries + 1 });
        }
        // 超过最大重试 → 丢弃
      }
    }

    setQueue(failed);
    persist(failed);
    setIsProcessing(false);
  }, [isProcessing, maxRetries, persist]);

  const flushRef = useRef(flush);
  flushRef.current = flush;

  const clear = useCallback(() => {
    setQueue([]);
    persist([]);
  }, [persist]);

  // 组件挂载时自动 flush
  useEffect(() => {
    if (autoFlush && navigator.onLine && queue.length > 0) {
      flush();
    }
  }, []);

  return {
    enqueue,
    queue,
    flush,
    clear,
    isOnline,
    isProcessing,
    size: queue.length,
  };
}

export default useOfflineQueue;
