/**
 * 键盘快捷键 Hook（零依赖）。
 *
 * 功能：
 * - useHotkeys：注册全局/局部键盘快捷键
 * - 支持组合键（Ctrl+Shift+K）
 * - 支持序列键（g then i）
 * - 输入框中忽略
 *
 * 用法：
 *   useHotkeys("ctrl+k", () => openPalette());
 *   useHotkeys(["ctrl+s", "ctrl+shift+s"], (e) => save(e));
 */

import { useCallback, useEffect, useRef } from "react";

type HotkeyHandler = (event: KeyboardEvent) => void;

interface UseHotkeysOptions {
  /** 是否启用 */
  enabled?: boolean;
  /** 在 input/textarea 中也触发 */
  enableInInputs?: boolean;
  /** 是否阻止默认行为 */
  preventDefault?: boolean;
  /** 作用域元素（不传则全局） */
  scopeRef?: React.RefObject<HTMLElement | null>;
}

interface ParsedHotkey {
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  meta: boolean;
  key: string;
}

function parseHotkey(combo: string): ParsedHotkey {
  const parts = combo.toLowerCase().split("+").map((p) => p.trim());
  return {
    ctrl: parts.includes("ctrl") || parts.includes("control"),
    shift: parts.includes("shift"),
    alt: parts.includes("alt") || parts.includes("option"),
    meta: parts.includes("meta") || parts.includes("cmd") || parts.includes("command"),
    key: parts.filter((p) => !["ctrl", "control", "shift", "alt", "option", "meta", "cmd", "command"].includes(p))[0] || "",
  };
}

function matchesEvent(parsed: ParsedHotkey, e: KeyboardEvent): boolean {
  const key = e.key.toLowerCase();
  const keyMatches = key === parsed.key || (parsed.key === "escape" && key === "esc");

  return (
    keyMatches &&
    e.ctrlKey === parsed.ctrl &&
    e.shiftKey === parsed.shift &&
    e.altKey === parsed.alt &&
    e.metaKey === parsed.meta
  );
}

function isInputElement(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
}

export function useHotkeys(
  keys: string | string[],
  handler: HotkeyHandler,
  options: UseHotkeysOptions = {},
): void {
  const { enabled = true, enableInInputs = false, preventDefault = true, scopeRef } = options;

  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const parsedKeysRef = useRef<ParsedHotkey[]>([]);
  parsedKeysRef.current = (Array.isArray(keys) ? keys : [keys]).map(parseHotkey);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;
      if (!enableInInputs && isInputElement(e.target)) return;

      for (const parsed of parsedKeysRef.current) {
        if (matchesEvent(parsed, e)) {
          if (preventDefault) {
            e.preventDefault();
            e.stopPropagation();
          }
          handlerRef.current(e);
          return;
        }
      }
    },
    [enabled, enableInInputs, preventDefault],
  );

  useEffect(() => {
    const target = scopeRef?.current || document;
    target.addEventListener("keydown", handleKeyDown as EventListener);
    return () => {
      target.removeEventListener("keydown", handleKeyDown as EventListener);
    };
  }, [handleKeyDown, scopeRef]);
}

/** 序列键 Hook：按顺序按下多个键触发（如 g → i）。 */
export function useKeySequence(
  sequence: string[],
  handler: () => void,
  options: { timeout?: number; enabled?: boolean } = {},
): void {
  const { timeout = 1000, enabled = true } = options;
  const bufferRef = useRef<string[]>([]);
  const timerRef = useRef<number>(0);
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!enabled) return;

    const onKey = (e: KeyboardEvent) => {
      if (isInputElement(e.target)) return;

      bufferRef.current.push(e.key.toLowerCase());
      clearTimeout(timerRef.current);

      // 检查是否匹配序列
      const buf = bufferRef.current;
      const seq = sequence.map((s) => s.toLowerCase());

      if (buf.length === seq.length && buf.every((k, i) => k === seq[i])) {
        bufferRef.current = [];
        handlerRef.current();
        return;
      }

      // 不匹配前缀则重置
      if (!seq.slice(0, buf.length).every((k, i) => k === buf[i])) {
        bufferRef.current = [];
      }

      // 超时重置
      timerRef.current = window.setTimeout(() => {
        bufferRef.current = [];
      }, timeout);
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      clearTimeout(timerRef.current);
    };
  }, [sequence, timeout, enabled]);
}

export default useHotkeys;
