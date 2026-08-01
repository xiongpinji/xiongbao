/**
 * 无限滚动 Hook（IntersectionObserver）。
 *
 * 功能：
 * - useInfiniteScroll：监听容器触底自动加载
 * - 支持加载状态 / 错误 / 无更多数据
 * - 防抖（避免重复触发）
 *
 * 用法：
 *   const { sentinelRef, isLoading, hasMore } = useInfiniteScroll({
 *     onLoadMore: async () => {
 *       const data = await fetchPage(page);
 *       setItems(prev => [...prev, ...data]);
 *       return data.length > 0; // 是否还有更多
 *     },
 *   });
 *   <div ref={sentinelRef} />
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseInfiniteScrollOptions {
  /** 加载更多回调，返回是否还有更多数据 */
  onLoadMore: () => Promise<boolean>;
  /** 是否启用（默认 true） */
  enabled?: boolean;
  /** 触发距离（px，默认 100） */
  threshold?: number;
}

interface UseInfiniteScrollReturn {
  /** 绑定到哨兵元素（列表底部） */
  sentinelRef: React.RefObject<HTMLDivElement | null>;
  isLoading: boolean;
  hasMore: boolean;
  error: string | null;
  /** 手动重置状态 */
  reset: () => void;
}

export function useInfiniteScroll({
  onLoadMore,
  enabled = true,
  threshold = 100,
}: UseInfiniteScrollOptions): UseInfiniteScrollReturn {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadingRef = useRef(false);
  const hasMoreRef = useRef(true);

  const loadMore = useCallback(async () => {
    if (loadingRef.current || !hasMoreRef.current || !enabled) return;

    loadingRef.current = true;
    setIsLoading(true);
    setError(null);

    try {
      const more = await onLoadMore();
      hasMoreRef.current = more;
      setHasMore(more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      loadingRef.current = false;
      setIsLoading(false);
    }
  }, [onLoadMore, enabled]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !enabled) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadMore();
        }
      },
      { rootMargin: `${threshold}px` },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore, enabled, threshold]);

  const reset = useCallback(() => {
    loadingRef.current = false;
    hasMoreRef.current = true;
    setIsLoading(false);
    setHasMore(true);
    setError(null);
  }, []);

  return { sentinelRef, isLoading, hasMore, error, reset };
}

export default useInfiniteScroll;
