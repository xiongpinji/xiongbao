/**
 * 主题系统：CSS Variables 动态切换。
 *
 * 支持：
 * - 暗色（默认）/ 亮色 / 自定义主题
 * - CSS 变量驱动，零闪烁
 * - localStorage 持久化
 * - useTheme Hook
 *
 * 用法：
 *   const { theme, setTheme, toggle } = useTheme();
 *   <button onClick={toggle}>切换主题</button>
 */

import { useCallback, useEffect, useState } from "react";

export type ThemeName = "dark" | "light" | "gold";

interface ThemeVars {
  "--bg-primary": string;
  "--bg-secondary": string;
  "--bg-tertiary": string;
  "--text-primary": string;
  "--text-secondary": string;
  "--text-muted": string;
  "--accent": string;
  "--accent-hover": string;
  "--border": string;
  "--shadow": string;
}

const THEMES: Record<ThemeName, ThemeVars> = {
  dark: {
    "--bg-primary": "#0a0a0a",
    "--bg-secondary": "#141414",
    "--bg-tertiary": "#1f1f1f",
    "--text-primary": "#f5f5f5",
    "--text-secondary": "#a3a3a3",
    "--text-muted": "#737373",
    "--accent": "#d6ad62",
    "--accent-hover": "#c49b52",
    "--border": "#262626",
    "--shadow": "rgba(0,0,0,0.5)",
  },
  light: {
    "--bg-primary": "#ffffff",
    "--bg-secondary": "#f8f8f8",
    "--bg-tertiary": "#f0f0f0",
    "--text-primary": "#171717",
    "--text-secondary": "#525252",
    "--text-muted": "#a3a3a3",
    "--accent": "#b8860b",
    "--accent-hover": "#996f09",
    "--border": "#e5e5e5",
    "--shadow": "rgba(0,0,0,0.1)",
  },
  gold: {
    "--bg-primary": "#0d0b08",
    "--bg-secondary": "#1a1610",
    "--bg-tertiary": "#262018",
    "--text-primary": "#f5e6d3",
    "--text-secondary": "#c4a882",
    "--text-muted": "#8b7355",
    "--accent": "#d6ad62",
    "--accent-hover": "#e8c47a",
    "--border": "#3d3225",
    "--shadow": "rgba(0,0,0,0.6)",
  },
};

const STORAGE_KEY = "xagent_theme";

function applyTheme(name: ThemeName) {
  const vars = THEMES[name];
  const root = document.documentElement;
  Object.entries(vars).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });
  root.setAttribute("data-theme", name);
}

function getStoredTheme(): ThemeName {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && stored in THEMES) return stored as ThemeName;
  return "dark";
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeName>(getStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((name: ThemeName) => {
    setThemeState(name);
    localStorage.setItem(STORAGE_KEY, name);
    applyTheme(name);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => {
      const next: ThemeName = prev === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      applyTheme(next);
      return next;
    });
  }, []);

  return { theme, setTheme, toggle, themes: Object.keys(THEMES) as ThemeName[] };
}

/** 初始化主题（在 App 挂载前调用，避免闪烁） */
export function initTheme() {
  applyTheme(getStoredTheme());
}
