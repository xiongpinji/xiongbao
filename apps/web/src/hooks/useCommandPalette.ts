/**
 * 命令面板 Hook（零依赖）。
 *
 * 功能：
 * - useCommandPalette：Ctrl+K 命令面板
 * - 模糊搜索命令
 * - 键盘导航（上/下/Enter）
 * - 分组 + 快捷键提示
 *
 * 用法：
 *   const { isOpen, open, close, query, setQuery, filtered, activeIndex } = useCommandPalette({
 *     commands: [
 *       { id: "new-agent", label: "新建 Agent", shortcut: "Ctrl+N", action: () => createAgent() },
 *       { id: "settings", label: "设置", group: "系统", action: () => openSettings() },
 *     ],
 *   });
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface Command {
  id: string;
  label: string;
  /** 分组 */
  group?: string;
  /** 快捷键提示 */
  shortcut?: string;
  /** 执行动作 */
  action: () => void;
  /** 关键词（辅助搜索） */
  keywords?: string[];
  /** 是否禁用 */
  disabled?: boolean;
}

interface UseCommandPaletteOptions {
  commands: Command[];
  /** 打开快捷键（默认 ctrl+k） */
  hotkey?: string;
  /** 执行后自动关闭（默认 true） */
  closeOnExecute?: boolean;
  /** 打开回调 */
  onOpen?: () => void;
  /** 关闭回调 */
  onClose?: () => void;
}

interface UseCommandPaletteReturn {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  query: string;
  setQuery: (q: string) => void;
  /** 过滤后的命令 */
  filtered: Command[];
  /** 当前高亮索引 */
  activeIndex: number;
  setActiveIndex: (i: number) => void;
  /** 执行命令 */
  execute: (cmd: Command) => void;
  /** 键盘事件处理（绑定到输入框） */
  onKeyDown: (e: React.KeyboardEvent) => void;
}

// 简单模糊匹配
function fuzzyMatch(text: string, query: string): boolean {
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  if (lower.includes(q)) return true;

  // 子序列匹配
  let qi = 0;
  for (let i = 0; i < lower.length && qi < q.length; i++) {
    if (lower[i] === q[qi]) qi++;
  }
  return qi === q.length;
}

export function useCommandPalette(
  options: UseCommandPaletteOptions,
): UseCommandPaletteReturn {
  const { commands, hotkey = "ctrl+k", closeOnExecute = true, onOpen, onClose } = options;

  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const open = useCallback(() => {
    setIsOpen(true);
    setQuery("");
    setActiveIndex(0);
    onOpen?.();
  }, [onOpen]);

  const close = useCallback(() => {
    setIsOpen(false);
    onClose?.();
  }, [onClose]);

  const toggle = useCallback(() => {
    if (isOpen) close();
    else open();
  }, [isOpen, open, close]);

  const execute = useCallback(
    (cmd: Command) => {
      if (cmd.disabled) return;
      cmd.action();
      if (closeOnExecute) close();
    },
    [closeOnExecute, close],
  );

  // 过滤
  const filtered = useMemo(() => {
    if (!query.trim()) return commands.filter((c) => !c.disabled);
    return commands.filter((c) => {
      if (c.disabled) return false;
      if (fuzzyMatch(c.label, query)) return true;
      if (c.keywords?.some((k) => fuzzyMatch(k, query))) return true;
      if (c.group && fuzzyMatch(c.group, query)) return true;
      return false;
    });
  }, [commands, query]);

  // 重置索引
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  // 全局快捷键
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const parts = hotkey.toLowerCase().split("+");
      const needCtrl = parts.includes("ctrl") || parts.includes("meta");
      const key = parts[parts.length - 1];

      if (needCtrl && !(e.ctrlKey || e.metaKey)) return;
      if (e.key.toLowerCase() !== key) return;

      e.preventDefault();
      toggle();
    };

    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [hotkey, toggle]);

  // 输入框键盘导航
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex((prev) => (prev + 1) % filtered.length);
          break;
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex((prev) => (prev - 1 + filtered.length) % filtered.length);
          break;
        case "Enter":
          e.preventDefault();
          if (filtered[activeIndex]) execute(filtered[activeIndex]);
          break;
        case "Escape":
          e.preventDefault();
          close();
          break;
      }
    },
    [filtered, activeIndex, execute, close],
  );

  return {
    isOpen,
    open,
    close,
    toggle,
    query,
    setQuery,
    filtered,
    activeIndex,
    setActiveIndex,
    execute,
    onKeyDown,
  };
}

export default useCommandPalette;
