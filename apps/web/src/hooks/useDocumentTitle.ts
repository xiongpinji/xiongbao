/**
 * 动态标题 Hook（零依赖）。
 *
 * 功能：
 * - useDocumentTitle：动态设置页面标题
 * - 未读消息数徽标
 * - 卸载时恢复原标题
 *
 * 用法：
 *   useDocumentTitle("Agent 详情");
 *   useDocumentTitle(`(${unread}) 消息`, { restoreOnUnmount: true });
 */

import { useEffect, useRef } from "react";

interface UseDocumentTitleOptions {
  /** 卸载时恢复原标题（默认 true） */
  restoreOnUnmount?: boolean;
  /** 是否禁用（默认 false） */
  disabled?: boolean;
  /** 标题前缀 */
  prefix?: string;
  /** 标题后缀 */
  suffix?: string;
}

export function useDocumentTitle(
  title: string,
  options: UseDocumentTitleOptions = {},
): void {
  const { restoreOnUnmount = true, disabled = false, prefix = "", suffix = "" } = options;
  const originalTitleRef = useRef<string>("");

  useEffect(() => {
    if (disabled || typeof document === "undefined") return;

    // 保存原始标题
    if (!originalTitleRef.current) {
      originalTitleRef.current = document.title;
    }

    const fullTitle = `${prefix}${title}${suffix}`;
    document.title = fullTitle;

    return () => {
      if (restoreOnUnmount) {
        document.title = originalTitleRef.current;
      }
    };
  }, [title, disabled, prefix, suffix, restoreOnUnmount]);
}

/** 未读消息标题闪烁 */
export function useUnreadTitle(
  unreadCount: number,
  baseTitle: string = "X-Agent",
): void {
  useEffect(() => {
    if (typeof document === "undefined") return;

    if (unreadCount > 0) {
      document.title = `(${unreadCount > 99 ? "99+" : unreadCount}) ${baseTitle}`;
    } else {
      document.title = baseTitle;
    }
  }, [unreadCount, baseTitle]);
}

export default useDocumentTitle;
