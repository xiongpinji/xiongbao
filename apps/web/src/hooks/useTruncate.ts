/**
 * 文本截断 Hook（零依赖）。
 *
 * 功能：
 * - useTruncate：按字符/单词截断文本
 * - 支持展开/收起
 * - 中文友好（不在词中间断开）
 *
 * 用法：
 *   const { text, isTruncated, toggle } = useTruncate(longText, { maxLength: 100 });
 *   <p>{text}</p>
 *   {isTruncated && <button onClick={toggle}>展开</button>}
 */

import { useCallback, useMemo, useState } from "react";

interface UseTruncateOptions {
  /** 最大字符数（默认 150） */
  maxLength?: number;
  /** 截断后缀（默认 "..."） */
  suffix?: string;
  /** 按单词截断（英文，默认 true） */
  wordBoundary?: boolean;
  /** 初始是否展开（默认 false） */
  defaultExpanded?: boolean;
}

interface UseTruncateReturn {
  /** 显示的文本 */
  text: string;
  /** 是否被截断 */
  isTruncated: boolean;
  /** 是否展开状态 */
  isExpanded: boolean;
  /** 切换展开/收起 */
  toggle: () => void;
  /** 展开 */
  expand: () => void;
  /** 收起 */
  collapse: () => void;
}

export function useTruncate(
  content: string,
  options: UseTruncateOptions = {},
): UseTruncateReturn {
  const {
    maxLength = 150,
    suffix = "...",
    wordBoundary = true,
    defaultExpanded = false,
  } = options;

  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const needsTruncation = content.length > maxLength;

  const text = useMemo(() => {
    if (!needsTruncation || isExpanded) return content;

    let truncated = content.slice(0, maxLength);

    // 按单词边界截断（英文）
    if (wordBoundary) {
      const lastSpace = truncated.lastIndexOf(" ");
      // 只在合理位置断词（避免只剩很少字符）
      if (lastSpace > maxLength * 0.6) {
        truncated = truncated.slice(0, lastSpace);
      }
    }

    // 去除末尾标点
    truncated = truncated.replace(/[,，、；;：:。\s]+$/, "");

    return truncated + suffix;
  }, [content, maxLength, suffix, wordBoundary, needsTruncation, isExpanded]);

  const toggle = useCallback(() => setIsExpanded((prev) => !prev), []);
  const expand = useCallback(() => setIsExpanded(true), []);
  const collapse = useCallback(() => setIsExpanded(false), []);

  return {
    text,
    isTruncated: needsTruncation,
    isExpanded,
    toggle,
    expand,
    collapse,
  };
}

export default useTruncate;
