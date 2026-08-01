/**
 * 快捷键绑定 Hook（零依赖）。
 *
 * 功能：
 * - useHotkeys：全局/局部键盘快捷键绑定
 * - 支持组合键（Ctrl+S, Shift+Enter）
 * - 输入框内自动忽略（可配置）
 * - 多快捷键同时注册
 *
 * 用法：
 *   useHotkeys([
 *     { keys: "ctrl+s", handler: (e) => save(), preventDefault: true },
 *     { keys: "escape", handler: () => close() },
 *   ]);
 */

import { useEffect, useRef } from "react";

interface HotkeyBinding {
  /** 快捷键描述（如 "ctrl+s", "shift+enter", "escape"） */
  keys: string;
  /** 触发回调 */
  handler: (event: KeyboardEvent) => void;
  /** 是否阻止默认行为（默认 false） */
  preventDefault?: boolean;
  /** 是否阻止冒泡（默认 false） */
  stopPropagation?: boolean;
  /** 是否在输入框中也触发（默认 false） */
  allowInInput?: boolean;
  /** 是否启用（默认 true） */
  enabled?: boolean;
}

interface ParsedKeys {
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  meta: boolean;
  key: string;
}

/** 解析快捷键字符串 */
function parseKeys(keys: string): ParsedKeys {
  const parts = keys.toLowerCase().split("+").map((p) => p.trim());
  return {
    ctrl: parts.includes("ctrl") || parts.includes("control"),
    shift: parts.includes("shift"),
    alt: parts.includes("alt"),
    meta: parts.includes("meta") || parts.includes("cmd") || parts.includes("command"),
    key: parts.filter(
      (p) => !["ctrl", "control", "shift", "alt", "meta", "cmd", "command"].includes(p),
    )[0] || "",
  };
}

/** 判断是否在输入元素中 */
function isInputElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    target.isContentEditable
  );
}

/** 匹配键盘事件 */
function matchEvent(event: KeyboardEvent, parsed: ParsedKeys): boolean {
  const eventKey = event.key.toLowerCase();
  const keyMatch =
    parsed.key === eventKey ||
    (parsed.key === "space" && eventKey === " ") ||
    (parsed.key === "esc" && eventKey === "escape");

  return (
    keyMatch &&
    event.ctrlKey === parsed.ctrl &&
    event.shiftKey === parsed.shift &&
    event.altKey === parsed.alt &&
    event.metaKey === parsed.meta
  );
}

export function useHotkeys(bindings: HotkeyBinding[]): void {
  const bindingsRef = useRef(bindings);
  bindingsRef.current = bindings;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const inInput = isInputElement(event.target);

      for (const binding of bindingsRef.current) {
        if (binding.enabled === false) continue;
        if (inInput && !binding.allowInInput) continue;

        const parsed = parseKeys(binding.keys);
        if (matchEvent(event, parsed)) {
          if (binding.preventDefault) event.preventDefault();
          if (binding.stopPropagation) event.stopPropagation();
          binding.handler(event);
          break; // 第一个匹配即停止
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, []);
}

export default useHotkeys;
