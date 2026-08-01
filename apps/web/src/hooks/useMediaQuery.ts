/**
 * 媒体查询 Hook（零依赖）。
 *
 * 功能：
 * - useMediaQuery：监听 CSS 媒体查询匹配状态
 * - useBreakpoint：预设断点快捷方式
 * - SSR 安全（服务端返回默认值）
 *
 * 用法：
 *   const isMobile = useMediaQuery("(max-width: 768px)");
 *   const { isMobile, isTablet, isDesktop } = useBreakpoint();
 */

import { useCallback, useEffect, useState } from "react";

/** 监听任意媒体查询 */
export function useMediaQuery(
  query: string,
  defaultValue: boolean = false,
): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined") return defaultValue;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mql = window.matchMedia(query);
    setMatches(mql.matches);

    const handler = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    // 兼容旧浏览器
    if (mql.addEventListener) {
      mql.addEventListener("change", handler);
      return () => mql.removeEventListener("change", handler);
    } else {
      mql.addListener(handler);
      return () => mql.removeListener(handler);
    }
  }, [query]);

  return matches;
}

// ─── 预设断点 ───

export const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
} as const;

interface BreakpointState {
  /** < 640px */
  isMobile: boolean;
  /** 640px - 1023px */
  isTablet: boolean;
  /** >= 1024px */
  isDesktop: boolean;
  /** >= 1280px */
  isWide: boolean;
  /**  prefers-reduced-motion */
  prefersReducedMotion: boolean;
  /** prefers-color-scheme: dark */
  prefersDark: boolean;
}

/** 预设断点 + 偏好检测 */
export function useBreakpoint(): BreakpointState {
  const isMobile = useMediaQuery(`(max-width: ${BREAKPOINTS.sm - 1}px)`);
  const isTablet = useMediaQuery(
    `(min-width: ${BREAKPOINTS.sm}px) and (max-width: ${BREAKPOINTS.lg - 1}px)`,
  );
  const isDesktop = useMediaQuery(`(min-width: ${BREAKPOINTS.lg}px)`);
  const isWide = useMediaQuery(`(min-width: ${BREAKPOINTS.xl}px)`);
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");

  return { isMobile, isTablet, isDesktop, isWide, prefersReducedMotion, prefersDark };
}

export default useMediaQuery;
