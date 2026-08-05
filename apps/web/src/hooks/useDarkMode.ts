/**
 * 深色模式检测 Hook（零依赖）。
 *
 * 功能：
 * - useDarkMode：检测系统深色模式偏好
 * - 监听变化（用户切换系统主题）
 * - 与 useTheme 配合使用
 *
 * 用法：
 *   const { isDark, isLight, preference } = useDarkMode();
 *   // 跟随系统：isDark 为 true 时应用暗色主题
 */

import { useEffect, useState } from "react";

type ColorSchemePreference = "dark" | "light" | "no-preference";

interface UseDarkModeReturn {
  /** 系统是否偏好深色 */
  isDark: boolean;
  /** 系统是否偏好浅色 */
  isLight: boolean;
  /** 偏好值 */
  preference: ColorSchemePreference;
  /** 是否支持检测 */
  isSupported: boolean;
}

function getPreference(): ColorSchemePreference {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "no-preference";
  }
  if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  if (window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "no-preference";
}

export function useDarkMode(): UseDarkModeReturn {
  const [preference, setPreference] = useState<ColorSchemePreference>(getPreference);

  const isSupported =
    typeof window !== "undefined" && "matchMedia" in window;

  useEffect(() => {
    if (!isSupported) return;

    const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const lightQuery = window.matchMedia("(prefers-color-scheme: light)");

    const handleChange = () => {
      setPreference(getPreference());
    };

    darkQuery.addEventListener("change", handleChange);
    lightQuery.addEventListener("change", handleChange);

    return () => {
      darkQuery.removeEventListener("change", handleChange);
      lightQuery.removeEventListener("change", handleChange);
    };
  }, [isSupported]);

  return {
    isDark: preference === "dark",
    isLight: preference === "light",
    preference,
    isSupported,
  };
}

export default useDarkMode;
