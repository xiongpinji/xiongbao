/**
 * 响应式间距 Hook（零依赖）。
 *
 * 功能：
 * - useSpacing：根据断点返回间距 token
 * - 统一设计系统间距
 * - 支持自定义 scale
 *
 * 用法：
 *   const sp = useSpacing();
 *   <div style={{ padding: sp.md, gap: sp.sm }} />
 */

import { useMemo } from "react";
import { useMediaQuery, BREAKPOINTS } from "./useMediaQuery";

interface SpacingScale {
  /** 2px */
  xxs: string;
  /** 4px */
  xs: string;
  /** 8px */
  sm: string;
  /** 12px */
  md: string;
  /** 16px */
  lg: string;
  /** 24px */
  xl: string;
  /** 32px */
  "2xl": string;
  /** 48px */
  "3xl": string;
  /** 64px */
  "4xl": string;
  /** 页面边距 */
  page: string;
  /** 区块间距 */
  section: string;
}

// 移动端间距
const MOBILE_SCALE: SpacingScale = {
  xxs: "2px",
  xs: "4px",
  sm: "6px",
  md: "10px",
  lg: "12px",
  xl: "16px",
  "2xl": "24px",
  "3xl": "32px",
  "4xl": "48px",
  page: "16px",
  section: "32px",
};

// 平板间距
const TABLET_SCALE: SpacingScale = {
  xxs: "2px",
  xs: "4px",
  sm: "8px",
  md: "12px",
  lg: "16px",
  xl: "20px",
  "2xl": "28px",
  "3xl": "40px",
  "4xl": "56px",
  page: "24px",
  section: "48px",
};

// 桌面间距
const DESKTOP_SCALE: SpacingScale = {
  xxs: "2px",
  xs: "4px",
  sm: "8px",
  md: "12px",
  lg: "16px",
  xl: "24px",
  "2xl": "32px",
  "3xl": "48px",
  "4xl": "64px",
  page: "32px",
  section: "64px",
};

/** 响应式间距 token */
export function useSpacing(): SpacingScale {
  const isMobile = useMediaQuery(`(max-width: ${BREAKPOINTS.sm - 1}px)`);
  const isTablet = useMediaQuery(
    `(min-width: ${BREAKPOINTS.sm}px) and (max-width: ${BREAKPOINTS.lg - 1}px)`,
  );

  return useMemo(() => {
    if (isMobile) return MOBILE_SCALE;
    if (isTablet) return TABLET_SCALE;
    return DESKTOP_SCALE;
  }, [isMobile, isTablet]);
}

/** 静态间距（不响应断点，用于固定布局） */
export const SPACING = DESKTOP_SCALE;

export default useSpacing;
