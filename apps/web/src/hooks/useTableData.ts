/**
 * 表格排序 / 筛选 / 分页 Hook（零依赖）。
 *
 * 功能：
 * - useTableData：客户端排序 + 筛选 + 分页
 * - 多列排序（可选）
 * - 文本搜索
 * - 分页控制
 *
 * 用法：
 *   const { sortedData, sortBy, toggleSort, sortState, page, setPage } = useTableData(items, {
 *     pageSize: 20,
 *     searchKeys: ["name", "email"],
 *   });
 */

import { useCallback, useMemo, useState } from "react";

type SortDirection = "asc" | "desc" | null;

interface SortState {
  key: string | null;
  direction: SortDirection;
}

interface UseTableDataOptions<T> {
  /** 每页数量（默认 20） */
  pageSize?: number;
  /** 搜索匹配的字段 */
  searchKeys?: (keyof T)[];
  /** 初始排序 */
  initialSort?: SortState;
  /** 自定义比较器 */
  comparators?: Partial<Record<keyof T, (a: T, b: T) => number>>;
}

interface UseTableDataReturn<T> {
  /** 当前页数据（已排序 + 筛选） */
  pageData: T[];
  /** 全部筛选后数据（未分页） */
  filteredData: T[];
  /** 排序状态 */
  sortState: SortState;
  /** 切换排序 */
  toggleSort: (key: string) => void;
  /** 搜索关键词 */
  search: string;
  /** 设置搜索 */
  setSearch: (value: string) => void;
  /** 当前页（从 1 开始） */
  page: number;
  /** 设置页码 */
  setPage: (page: number) => void;
  /** 总页数 */
  totalPages: number;
  /** 总条数 */
  totalCount: number;
  /** 重置所有状态 */
  reset: () => void;
}

export function useTableData<T extends Record<string, any>>(
  data: T[],
  options: UseTableDataOptions<T> = {},
): UseTableDataReturn<T> {
  const {
    pageSize = 20,
    searchKeys = [],
    initialSort = { key: null, direction: null },
    comparators = {},
  } = options;

  const [sortState, setSortState] = useState<SortState>(initialSort);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  // 切换排序
  const toggleSort = useCallback((key: string) => {
    setSortState((prev) => {
      if (prev.key !== key) {
        return { key, direction: "asc" };
      }
      // asc → desc → null → asc
      if (prev.direction === "asc") return { key, direction: "desc" };
      if (prev.direction === "desc") return { key: null, direction: null };
      return { key, direction: "asc" };
    });
    setPage(1);
  }, []);

  // 搜索筛选
  const filteredData = useMemo(() => {
    if (!search.trim()) return data;

    const keyword = search.toLowerCase().trim();
    return data.filter((item) =>
      searchKeys.some((key) => {
        const value = item[key];
        if (value == null) return false;
        return String(value).toLowerCase().includes(keyword);
      }),
    );
  }, [data, search, searchKeys]);

  // 排序
  const sortedData = useMemo(() => {
    if (!sortState.key || !sortState.direction) return filteredData;

    const { key, direction } = sortState;
    const sorted = [...filteredData].sort((a, b) => {
      // 自定义比较器
      const custom = comparators[key as keyof T];
      if (custom) {
        return direction === "asc" ? custom(a, b) : -custom(a, b);
      }

      // 默认比较
      const aVal = a[key];
      const bVal = b[key];

      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return direction === "asc" ? aVal - bVal : bVal - aVal;
      }

      const aStr = String(aVal).toLowerCase();
      const bStr = String(bVal).toLowerCase();
      const cmp = aStr.localeCompare(bStr, "zh-CN");
      return direction === "asc" ? cmp : -cmp;
    });

    return sorted;
  }, [filteredData, sortState, comparators]);

  // 分页
  const totalCount = sortedData.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const safePage = Math.min(page, totalPages);

  const pageData = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, safePage, pageSize]);

  const reset = useCallback(() => {
    setSortState(initialSort);
    setSearch("");
    setPage(1);
  }, [initialSort]);

  return {
    pageData,
    filteredData: sortedData,
    sortState,
    toggleSort,
    search,
    setSearch: (v: string) => {
      setSearch(v);
      setPage(1);
    },
    page: safePage,
    setPage,
    totalPages,
    totalCount,
    reset,
  };
}

export default useTableData;
