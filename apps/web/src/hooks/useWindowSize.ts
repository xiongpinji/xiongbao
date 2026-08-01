/**
 * 窗口尺寸 / 媒体查询 Hooks（零依赖）。
 *
 * - useWindowSize：实时窗口宽高
 * - useMediaQuery：CSS 媒体查询匹配
 * - useBreakpoint：响应式断点
 *
 * 用法：
 *   const { width, height } = useWindowSize();
 *   const isMobile = useMediaQuery("(max-width: 768px)");
 *   const bp = useBreakpoint(); // "sm" | "md" | "lg" | "xl"
 */

import { useCallback, useEffect, useState } from "react";

interface WindowSize {
  width: number;
  height: number;
}

/**
 * 实时窗口尺寸。
 */
export function useWindowSize(): WindowSize {
  const [size, setSize] = useState<WindowSize>({
    width: typeof window !== "undefined" ? window.innerWidth : 1280,
    height: typeof window !== "undefined" ? window.innerHeight : 800,
  });

  useEffect(() => {
    let rafId: number;
    const handleResize = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        setSize({ width: window.innerWidth, height: window.innerHeight });
      });
    };

    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(rafId);
    };
  }, []);

  return size;
}

/**
 * CSS 媒体查询匹配。
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);

    setMatches(mql.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

export type Breakpoint = "sm" | "md" | "lg" | "xl" | "2xl";

const BREAKPOINTS: Record<Breakpoint, number> = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
};

/**
 * 响应式断点（基于 Tailwind 默认值）。
 */
export function useBreakpoint(): Breakpoint {
  const { width } = useWindowSize();

  if (width >= BREAKPOINTS["2xl"]) return "2xl";
  if (width >= BREAKPOINTS.xl) return "xl";
  if (width >= BREAKPOINTS.lg) return "lg";
  if (width >= BREAKPOINTS.md) return "md";
  return "sm";
}

/** 快捷：是否移动端 */
export function useIsMobile(): boolean {
  return useMediaQuery("(max-width: 767px)");
}
