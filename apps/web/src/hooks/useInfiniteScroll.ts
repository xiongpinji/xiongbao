/**
 * 无限滚动 Hook（零依赖）。
 *
 * 功能：
 * - useInfiniteScroll：触底自动加载下一页
 * - IntersectionObserver 检测哨兵元素
 * - 加载状态 + 错误处理 + 是否还有更多
 *
 * 用法：
 *   const { sentinelRef, isLoading, error } = useInfiniteScroll({
 *     fetchMore: async (page) => api.getItems(page),
 *     hasNextPage: true,
 *   });
 *   <div ref={sentinelRef} />
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseInfiniteScrollOptions {
  /** 加载下一页函数 */
  fetchMore: (page: number) => Promise<void>;
  /** 是否还有下一页 */
  hasNextPage: boolean;
  /** IntersectionObserver rootMargin（默认 200px） */
  rootMargin?: string;
  /** 阈值（默认 0） */
  threshold?: number;
  /** 是否禁用 */
  disabled?: boolean;
}

interface UseInfiniteScrollReturn {
  /** 哨兵元素 ref */
  sentinelRef: React.RefObject<HTMLDivElement | null>;
  /** 是否加载中 */
  isLoading: boolean;
  /** 错误信息 */
  error: Error | null;
  /** 当前页码 */
  page: number;
  /** 重置到第一页 */
  reset: () => void;
}

export function useInfiniteScroll(
  options: UseInfiniteScrollOptions,
): UseInfiniteScrollReturn {
  const {
    fetchMore,
    hasNextPage,
    rootMargin = "200px",
    threshold = 0,
    disabled = false,
  } = options;

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [page, setPage] = useState(1);
  const isLoadingRef = useRef(false);
  const pageRef = useRef(1);

  const loadMore = useCallback(async () => {
    if (isLoadingRef.current || !hasNextPage || disabled) return;

    isLoadingRef.current = true;
    setIsLoading(true);
    setError(null);

    try {
      await fetchMore(pageRef.current);
      pageRef.current += 1;
      setPage(pageRef.current);
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Load more failed"));
    } finally {
      isLoadingRef.current = false;
      setIsLoading(false);
    }
  }, [fetchMore, hasNextPage, disabled]);

  const reset = useCallback(() => {
    pageRef.current = 1;
    setPage(1);
    setError(null);
    setIsLoading(false);
    isLoadingRef.current = false;
  }, []);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || disabled) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadMore();
        }
      },
      { rootMargin, threshold },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore, rootMargin, threshold, disabled]);

  return { sentinelRef, isLoading, error, page, reset };
}

export default useInfiniteScroll;
