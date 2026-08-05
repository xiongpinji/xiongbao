/**
 * 无限滚动 Hook（零依赖）。
 *
 * 功能：
 * - useInfiniteScroll：触底自动加载
 * - 基于 IntersectionObserver
 * - 加载状态/错误/完成
 *
 * 用法：
 *   const { sentinelRef, isLoading } = useInfiniteScroll(loadMore, { hasMore });
 *   <div ref={sentinelRef} />
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseInfiniteScrollOptions {
  /** 是否还有更多数据 */
  hasMore?: boolean;
  /** 预加载距离 */
  rootMargin?: string;
  /** 加载失败回调 */
  onError?: (error: Error) => void;
}

interface UseInfiniteScrollReturn {
  /** 哨兵元素 ref */
  sentinelRef: React.RefCallback<HTMLElement>;
  /** 是否加载中 */
  isLoading: boolean;
  /** 错误 */
  error: Error | null;
  /** 手动触发加载 */
  loadMore: () => void;
}

export function useInfiniteScroll(
  fetchFn: () => Promise<void>,
  options: UseInfiniteScrollOptions = {},
): UseInfiniteScrollReturn {
  const { hasMore = true, rootMargin = "200px", onError } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadingRef = useRef(false);
  const fetchRef = useRef(fetchFn);
  fetchRef.current = fetchFn;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const doLoad = useCallback(async () => {
    if (loadingRef.current || !hasMore) return;
    loadingRef.current = true;
    setIsLoading(true);
    setError(null);

    try {
      await fetchRef.current();
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e));
      setError(err);
      onErrorRef.current?.(err);
    } finally {
      loadingRef.current = false;
      setIsLoading(false);
    }
  }, [hasMore]);

  const sentinelRef = useCallback(
    (el: HTMLElement | null) => {
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }

      if (!el || !hasMore) return;

      observerRef.current = new IntersectionObserver(
        (entries) => {
          if (entries[0]?.isIntersecting && !loadingRef.current) {
            doLoad();
          }
        },
        { rootMargin },
      );

      observerRef.current.observe(el);
    },
    [hasMore, rootMargin, doLoad],
  );

  useEffect(() => {
    return () => observerRef.current?.disconnect();
  }, []);

  return { sentinelRef, isLoading, error, loadMore: doLoad };
}

export default useInfiniteScroll;
