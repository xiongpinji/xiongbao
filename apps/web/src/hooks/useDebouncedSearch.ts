/**
 * 防抖搜索 Hook（零依赖）。
 *
 * 功能：
 * - useDebouncedSearch：输入防抖 + 搜索状态管理
 * - 自动取消过期请求
 * - 支持最小字符数触发
 * - 搜索结果 + 加载 + 错误
 *
 * 用法：
 *   const { query, setQuery, results, isLoading } = useDebouncedSearch({
 *     searchFn: async (q) => api.search(q),
 *     debounceMs: 300,
 *     minChars: 2,
 *   });
 *   <input value={query} onChange={(e) => setQuery(e.target.value)} />
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseDebouncedSearchOptions<T> {
  /** 搜索函数 */
  searchFn: (query: string) => Promise<T[]>;
  /** 防抖时间（ms，默认 300） */
  debounceMs?: number;
  /** 最少输入字符数（默认 1） */
  minChars?: number;
  /** 初始查询 */
  initialQuery?: string;
}

interface UseDebouncedSearchReturn<T> {
  /** 当前输入值 */
  query: string;
  /** 设置输入值 */
  setQuery: (q: string) => void;
  /** 搜索结果 */
  results: T[];
  /** 是否搜索中 */
  isLoading: boolean;
  /** 错误信息 */
  error: Error | null;
  /** 是否有搜索（输入达到最小字符） */
  isActive: boolean;
  /** 清空 */
  clear: () => void;
}

export function useDebouncedSearch<T>(
  options: UseDebouncedSearchOptions<T>,
): UseDebouncedSearchReturn<T> {
  const { searchFn, debounceMs = 300, minChars = 1, initialQuery = "" } = options;

  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<T[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef(0); // 请求版本号
  const searchFnRef = useRef(searchFn);
  searchFnRef.current = searchFn;

  useEffect(() => {
    // 清除之前的防抖
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    // 不满足最小字符
    if (query.trim().length < minChars) {
      setResults([]);
      setIsLoading(false);
      setError(null);
      return;
    }

    setIsLoading(true);

    timerRef.current = setTimeout(async () => {
      const version = ++abortRef.current;

      try {
        const data = await searchFnRef.current(query.trim());
        // 仅接受最新请求的结果
        if (version === abortRef.current) {
          setResults(data);
          setError(null);
          setIsLoading(false);
        }
      } catch (err) {
        if (version === abortRef.current) {
          setError(err instanceof Error ? err : new Error("Search failed"));
          setIsLoading(false);
        }
      }
    }, debounceMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [query, debounceMs, minChars]);

  const clear = useCallback(() => {
    setQuery("");
    setResults([]);
    setError(null);
    setIsLoading(false);
    abortRef.current++;
  }, []);

  return {
    query,
    setQuery,
    results,
    isLoading,
    error,
    isActive: query.trim().length >= minChars,
    clear,
  };
}

export default useDebouncedSearch;
