/**
 * 全局快捷键系统（零依赖）。
 *
 * 功能：
 * - useHotkeys Hook：注册组合键回调
 * - 支持 Ctrl/Cmd + Key 组合
 * - 输入框内自动忽略
 * - 快捷键帮助面板数据
 *
 * 用法：
 *   useHotkeys("ctrl+k", () => openSearch());
 *   useHotkeys("ctrl+shift+n", () => newChat());
 */

import { useEffect, useRef, useCallback } from "react";

interface HotkeyBinding {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  handler: () => void;
  description?: string;
}

// 全局注册表（用于帮助面板）
const registry: HotkeyBinding[] = [];

function parseHotkey(combo: string): Omit<HotkeyBinding, "handler" | "description"> {
  const parts = combo.toLowerCase().split("+");
  return {
    key: parts[parts.length - 1],
    ctrl: parts.includes("ctrl") || parts.includes("cmd") || parts.includes("meta"),
    shift: parts.includes("shift"),
    alt: parts.includes("alt"),
  };
}

function isInputFocused(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || (el as HTMLElement).isContentEditable;
}

/**
 * 注册全局快捷键。
 * @param combo 格式: "ctrl+k", "ctrl+shift+n", "alt+s"
 * @param handler 触发回调
 * @param description 描述（用于帮助面板）
 */
export function useHotkeys(combo: string, handler: () => void, description?: string) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const parsed = parseHotkey(combo);

  useEffect(() => {
    const binding: HotkeyBinding = { ...parsed, handler: () => handlerRef.current(), description };
    registry.push(binding);

    const onKeyDown = (e: KeyboardEvent) => {
      // 输入框内忽略（除非是 Escape）
      if (isInputFocused() && parsed.key !== "escape") return;

      const ctrlMatch = parsed.ctrl ? (e.ctrlKey || e.metaKey) : !(e.ctrlKey || e.metaKey);
      const shiftMatch = parsed.shift ? e.shiftKey : !e.shiftKey;
      const altMatch = parsed.alt ? e.altKey : !e.altKey;
      const keyMatch = e.key.toLowerCase() === parsed.key;

      if (ctrlMatch && shiftMatch && altMatch && keyMatch) {
        e.preventDefault();
        e.stopPropagation();
        handlerRef.current();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      const idx = registry.indexOf(binding);
      if (idx >= 0) registry.splice(idx, 1);
    };
  }, [combo]);
}

/** 获取所有已注册快捷键（帮助面板用） */
export function getRegisteredHotkeys(): { combo: string; description: string }[] {
  return registry
    .filter((b) => b.description)
    .map((b) => {
      const parts: string[] = [];
      if (b.ctrl) parts.push("Ctrl");
      if (b.shift) parts.push("Shift");
      if (b.alt) parts.push("Alt");
      parts.push(b.key.toUpperCase());
      return { combo: parts.join(" + "), description: b.description! };
    });
}

// ─── 预设快捷键常量 ───

export const HOTKEYS = {
  SEARCH: "ctrl+k",
  NEW_CHAT: "ctrl+shift+n",
  SETTINGS: "ctrl+,",
  SIDEBAR_TOGGLE: "ctrl+b",
  HELP: "ctrl+/",
  ESCAPE: "escape",
} as const;
