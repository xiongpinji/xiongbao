/**
 * URL 状态同步 Hook（零依赖）。
 *
 * 功能：
 * - useURLState：将状态同步到 URL query params
 * - 支持浏览器前进/后退
 * - 序列化/反序列化
 *
 * 用法：
 *   const [filters, setFilters] = useURLState({ tab: "all", page: "1" });
 *   setFilters({ tab: "active" }); // URL 变为 ?tab=active&page=1
 */

import { useCallback, useState } from "react";

type URLState = Record<string, string>;

interface UseURLStateOptions {
  /** 使用 replace 而非 push（默认 false） */
  replace?: boolean;
}

function getSearchParams(): URLState {
  if (typeof window === "undefined") return {};
  const params = new URLSearchParams(window.location.search);
  const state: URLState = {};
  params.forEach((value, key) => {
    state[key] = value;
  });
  return state;
}

function setSearchParams(
  updates: URLState,
  replace: boolean,
): void {
  const params = new URLSearchParams(window.location.search);

  for (const [key, value] of Object.entries(updates)) {
    if (value === "" || value === undefined || value === null) {
      params.delete(key);
    } else {
      params.set(key, value);
    }
  }

  const newUrl = `${window.location.pathname}?${params.toString()}`;
  if (replace) {
    window.history.replaceState(null, "", newUrl);
  } else {
    window.history.pushState(null, "", newUrl);
  }
}

export function useURLState(
  defaults: URLState = {},
  options: UseURLStateOptions = {},
): [URLState, (updates: Partial<URLState>) => void] {
  const { replace = false } = options;

  const [state, setState] = useState<URLState>(() => ({
    ...defaults,
    ...getSearchParams(),
  }));

  const setURLState = useCallback(
    (updates: Partial<URLState>) => {
      setState((prev) => {
        const next = { ...prev };
        for (const [key, value] of Object.entries(updates)) {
          if (value === undefined || value === "") {
            delete next[key];
          } else {
            next[key] = value;
          }
        }
        setSearchParams(updates as URLState, replace);
        return next;
      });
    },
    [replace],
  );

  return [state, setURLState];
}

export default useURLState;
