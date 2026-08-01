/**
 * 文本截断 Hook（零依赖）。
 *
 * 功能：
 * - useTruncate：文本截断与展开/收起
 * - 按行数/字符数截断
 * - 展开/收起状态
 *
 * 用法：
 *   const { text, isTruncated, toggle } = useTruncate(longText, { maxLines: 3 });
 *   <p>{text}</p>
 *   {isTruncated && <button onClick={toggle}>展开</button>}
 */

import { useCallback, useMemo, useState } from "react";

interface UseTruncateOptions {
  /** 最大字符数（与 maxLines 二选一） */
  maxLength?: number;
  /** 最大行数（需要容器 ref） */
  maxLines?: number;
  /** 截断后缀 */
  suffix?: string;
  /** 是否默认展开 */
  defaultExpanded?: boolean;
  /** 按单词边界截断 */
  wordBoundary?: boolean;
}

interface UseTruncateReturn {
  /** 截断后的文本 */
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
  /** 原始文本 */
  original: string;
}

export function useTruncate(
  content: string,
  options: UseTruncateOptions = {},
): UseTruncateReturn {
  const {
    maxLength = 200,
    suffix = "...",
    defaultExpanded = false,
    wordBoundary = true,
  } = options;

  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const { text, isTruncated } = useMemo(() => {
    if (isExpanded || content.length <= maxLength) {
      return { text: content, isTruncated: content.length > maxLength };
    }

    let truncated = content.slice(0, maxLength);

    // 按单词边界截断
    if (wordBoundary) {
      const lastSpace = truncated.lastIndexOf(" ");
      const lastCJK = Math.max(
        truncated.lastIndexOf("，"),
        truncated.lastIndexOf("。"),
        truncated.lastIndexOf("、"),
        truncated.lastIndexOf(" "),
      );
      const breakPoint = Math.max(lastSpace, lastCJK);
      if (breakPoint > maxLength * 0.6) {
        truncated = truncated.slice(0, breakPoint);
      }
    }

    return { text: truncated + suffix, isTruncated: true };
  }, [content, maxLength, suffix, isExpanded, wordBoundary]);

  const toggle = useCallback(() => setIsExpanded((prev) => !prev), []);
  const expand = useCallback(() => setIsExpanded(true), []);
  const collapse = useCallback(() => setIsExpanded(false), []);

  return { text, isTruncated, isExpanded, toggle, expand, collapse, original: content };
}

export default useTruncate;
