/**
 * 分页 Hook（零依赖）。
 *
 * 功能：
 * - usePagination：分页状态管理
 * - 页码范围计算
 * - 上一页/下一页/跳转
 *
 * 用法：
 *   const { page, pages, setPage, next, prev, range } = usePagination({ total: 100, pageSize: 10 });
 */

import { useCallback, useMemo, useState } from "react";

interface UsePaginationOptions {
  /** 总条目数 */
  total: number;
  /** 每页大小（默认 10） */
  pageSize?: number;
  /** 初始页码（默认 1） */
  initialPage?: number;
  /** 页码变化回调 */
  onChange?: (page: number) => void;
}

interface UsePaginationReturn {
  /** 当前页码（1-based） */
  page: number;
  /** 总页数 */
  totalPages: number;
  /** 设置页码 */
  setPage: (page: number) => void;
  /** 下一页 */
  next: () => void;
  /** 上一页 */
  prev: () => void;
  /** 第一页 */
  first: () => void;
  /** 最后一页 */
  last: () => void;
  /** 是否有下一页 */
  hasNext: boolean;
  /** 是否有上一页 */
  hasPrev: boolean;
  /** 当前页起始索引（0-based） */
  startIndex: number;
  /** 当前页结束索引 */
  endIndex: number;
  /** 可见页码范围 */
  range: number[];
}

export function usePagination(options: UsePaginationOptions): UsePaginationReturn {
  const { total, pageSize = 10, initialPage = 1, onChange } = options;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const [page, setPageState] = useState(Math.min(initialPage, totalPages));

  const setPage = useCallback(
    (p: number) => {
      const clamped = Math.max(1, Math.min(p, totalPages));
      setPageState(clamped);
      onChange?.(clamped);
    },
    [totalPages, onChange],
  );

  const next = useCallback(() => setPage(page + 1), [page, setPage]);
  const prev = useCallback(() => setPage(page - 1), [page, setPage]);
  const first = useCallback(() => setPage(1), [setPage]);
  const last = useCallback(() => setPage(totalPages), [totalPages, setPage]);

  const range = useMemo(() => {
    const delta = 2;
    const start = Math.max(1, page - delta);
    const end = Math.min(totalPages, page + delta);
    const pages: number[] = [];
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }, [page, totalPages]);

  return {
    page,
    totalPages,
    setPage,
    next,
    prev,
    first,
    last,
    hasNext: page < totalPages,
    hasPrev: page > 1,
    startIndex: (page - 1) * pageSize,
    endIndex: Math.min(page * pageSize - 1, total - 1),
    range,
  };
}

export default usePagination;
