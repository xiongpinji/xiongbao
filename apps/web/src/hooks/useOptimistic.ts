/**
 * 乐观更新 Hook（零依赖）。
 *
 * 功能：
 * - useOptimistic：先更新 UI 再等服务端确认
 * - 失败自动回滚
 * - 支持列表增/删/改
 *
 * 用法：
 *   const { data, optimisticUpdate, optimisticAdd, optimisticRemove } = useOptimistic(items);
 *   // 编辑：立即更新 UI，后台同步
 *   optimisticUpdate(id, { name: "new" }, () => api.update(id, { name: "new" }));
 */

import { useCallback, useRef, useState } from "react";

interface UseOptimisticReturn<T extends { id: string }> {
  /** 当前数据（含乐观更新） */
  data: T[];
  /** 乐观更新某项 */
  optimisticUpdate: (
    id: string,
    changes: Partial<T>,
    serverFn: () => Promise<any>,
  ) => Promise<void>;
  /** 乐观新增 */
  optimisticAdd: (item: T, serverFn: () => Promise<any>) => Promise<void>;
  /** 乐观删除 */
  optimisticRemove: (id: string, serverFn: () => Promise<any>) => Promise<void>;
  /** 是否有进行中的乐观操作 */
  isPending: boolean;
  /** 最近错误 */
  error: Error | null;
  /** 手动设置数据（服务端同步后） */
  setData: (data: T[]) => void;
}

export function useOptimistic<T extends { id: string }>(
  initialData: T[],
): UseOptimisticReturn<T> {
  const [data, setData] = useState<T[]>(initialData);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const pendingCount = useRef(0);

  const trackStart = useCallback(() => {
    pendingCount.current += 1;
    setIsPending(true);
  }, []);

  const trackEnd = useCallback(() => {
    pendingCount.current -= 1;
    if (pendingCount.current <= 0) {
      pendingCount.current = 0;
      setIsPending(false);
    }
  }, []);

  const optimisticUpdate = useCallback(
    async (id: string, changes: Partial<T>, serverFn: () => Promise<any>) => {
      setError(null);
      trackStart();

      // 保存快照
      const snapshot = data;

      // 乐观更新
      setData((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...changes } : item)),
      );

      try {
        await serverFn();
      } catch (e) {
        // 回滚
        setData(snapshot);
        setError(e instanceof Error ? e : new Error("Update failed"));
      } finally {
        trackEnd();
      }
    },
    [data, trackStart, trackEnd],
  );

  const optimisticAdd = useCallback(
    async (item: T, serverFn: () => Promise<any>) => {
      setError(null);
      trackStart();

      const snapshot = data;

      // 乐观新增
      setData((prev) => [...prev, item]);

      try {
        await serverFn();
      } catch (e) {
        // 回滚
        setData(snapshot);
        setError(e instanceof Error ? e : new Error("Add failed"));
      } finally {
        trackEnd();
      }
    },
    [data, trackStart, trackEnd],
  );

  const optimisticRemove = useCallback(
    async (id: string, serverFn: () => Promise<any>) => {
      setError(null);
      trackStart();

      const snapshot = data;

      // 乐观删除
      setData((prev) => prev.filter((item) => item.id !== id));

      try {
        await serverFn();
      } catch (e) {
        // 回滚
        setData(snapshot);
        setError(e instanceof Error ? e : new Error("Remove failed"));
      } finally {
        trackEnd();
      }
    },
    [data, trackStart, trackEnd],
  );

  return {
    data,
    optimisticUpdate,
    optimisticAdd,
    optimisticRemove,
    isPending,
    error,
    setData,
  };
}

export default useOptimistic;
