/**
 * CSS 变量主题 Hook（零依赖）。
 *
 * 功能：
 * - useThemeVars：动态 CSS 变量主题管理
 * - 预设主题（dark/light/gold）
 * - 运行时切换 + 持久化
 * - 自定义变量覆盖
 *
 * 用法：
 *   const { theme, setTheme, vars } = useThemeVars("dark");
 *   <div style={{ background: vars.bg, color: vars.text }}>...</div>
 */

import { useCallback, useEffect, useMemo, useState } from "react";

interface ThemeVars {
  bg: string;
  bgSecondary: string;
  text: string;
  textSecondary: string;
  accent: string;
  border: string;
  shadow: string;
  [key: string]: string;
}

type ThemeName = "dark" | "light" | "gold" | string;

// 预设主题
const THEMES: Record<string, ThemeVars> = {
  dark: {
    bg: "#0a0a0a",
    bgSecondary: "#141414",
    text: "#e5e5e5",
    textSecondary: "#a3a3a3",
    accent: "#f5f5f5",
    border: "#262626",
    shadow: "rgba(0,0,0,0.4)",
  },
  light: {
    bg: "#ffffff",
    bgSecondary: "#f5f5f7",
    text: "#1a1a2e",
    textSecondary: "#6b7280",
    accent: "#171717",
    border: "#e5e7eb",
    shadow: "rgba(0,0,0,0.1)",
  },
  gold: {
    bg: "#0a0a0a",
    bgSecondary: "#171717",
    text: "#f5f5f5",
    textSecondary: "#a3a3a3",
    accent: "#fafafa",
    border: "#262626",
    shadow: "rgba(0,0,0,0.3)",
  },
};

const STORAGE_KEY = "xagent_theme";

function loadSavedTheme(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function useThemeVars(
  defaultTheme: ThemeName = "dark",
): {
  theme: string;
  setTheme: (name: ThemeName) => void;
  vars: ThemeVars;
  themes: string[];
  setVar: (key: string, value: string) => void;
} {
  const [theme, setThemeState] = useState<string>(
    () => loadSavedTheme() || defaultTheme,
  );
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const vars = useMemo((): ThemeVars => {
    const base = THEMES[theme] || THEMES.dark;
    return { ...base, ...overrides };
  }, [theme, overrides]);

  const setTheme = useCallback((name: ThemeName) => {
    setThemeState(name);
    setOverrides({});
    try {
      localStorage.setItem(STORAGE_KEY, name);
    } catch {
      // 忽略
    }
  }, []);

  const setVar = useCallback((key: string, value: string) => {
    setOverrides((prev) => ({ ...prev, [key]: value }));
  }, []);

  // 注入 CSS 变量到 :root
  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    Object.entries(vars).forEach(([key, value]) => {
      // camelCase → kebab-case
      const cssKey = `--theme-${key.replace(/([A-Z])/g, "-$1").toLowerCase()}`;
      root.style.setProperty(cssKey, value);
    });
  }, [vars]);

  const themes = useMemo(() => Object.keys(THEMES), []);

  return { theme, setTheme, vars, themes, setVar };
}

export default useThemeVars;
