/**
 * 媒体查询 Hook（零依赖）。
 *
 * 功能：
 * - useMediaQuery：响应式 CSS 媒体查询匹配
 * - 预置断点（sm/md/lg/xl/2xl）
 * - 实时监听变化
 *
 * 用法：
 *   const isMobile = useMediaQuery("(max-width: 768px)");
 *   const { isDesktop, isTablet } = useBreakpoints();
 */

import { useCallback, useEffect, useState } from "react";

/** 监听单个媒体查询。 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);

    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);

    // 兼容旧浏览器
    if (mql.addEventListener) {
      mql.addEventListener("change", handler);
      return () => mql.removeEventListener("change", handler);
    }
    mql.addListener(handler);
    return () => mql.removeListener(handler);
  }, [query]);

  return matches;
}

/** Tailwind 断点。 */
export const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
} as const;

interface UseBreakpointsReturn {
  /** >= 640px */
  isSm: boolean;
  /** >= 768px */
  isMd: boolean;
  /** >= 1024px */
  isLg: boolean;
  /** >= 1280px */
  isXl: boolean;
  /** >= 1536px */
  is2xl: boolean;
  /** < 768px */
  isMobile: boolean;
  /** 768px - 1023px */
  isTablet: boolean;
  /** >= 1024px */
  isDesktop: boolean;
}

/** 预置断点 Hook。 */
export function useBreakpoints(): UseBreakpointsReturn {
  const isSm = useMediaQuery(`(min-width: ${BREAKPOINTS.sm}px)`);
  const isMd = useMediaQuery(`(min-width: ${BREAKPOINTS.md}px)`);
  const isLg = useMediaQuery(`(min-width: ${BREAKPOINTS.lg}px)`);
  const isXl = useMediaQuery(`(min-width: ${BREAKPOINTS.xl}px)`);
  const is2xl = useMediaQuery(`(min-width: ${BREAKPOINTS["2xl"]}px)`);

  return {
    isSm,
    isMd,
    isLg,
    isXl,
    is2xl,
    isMobile: !isMd,
    isTablet: isMd && !isLg,
    isDesktop: isLg,
  };
}

/** 监听 prefers-color-scheme。 */
export function usePrefersDark(): boolean {
  return useMediaQuery("(prefers-color-scheme: dark)");
}

/** 监听 prefers-reduced-motion。 */
export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}

export default useMediaQuery;
