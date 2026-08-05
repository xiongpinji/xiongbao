/**
 * 滚动位置恢复 Hook（零依赖）。
 *
 * 功能：
 * - useScrollRestore：路由切换后恢复滚动位置
 * - useScrollToTop：路由切换后滚动到顶部
 * - 支持 sessionStorage 持久化
 *
 * 用法：
 *   const { saveScroll, restoreScroll } = useScrollRestore("page-key");
 *   // 离开前保存
 *   saveScroll();
 *   // 进入后恢复
 *   useEffect(() => restoreScroll(), []);
 */

import { useCallback, useEffect, useRef } from "react";

const STORAGE_PREFIX = "scroll_restore_";

interface UseScrollRestoreOptions {
  /** 使用 sessionStorage 持久化（默认 true） */
  persist?: boolean;
  /** 恢复延迟（ms，等待渲染，默认 100） */
  delay?: number;
  /** 滚动行为 */
  behavior?: ScrollBehavior;
}

interface UseScrollRestoreReturn {
  /** 保存当前滚动位置 */
  saveScroll: () => void;
  /** 恢复滚动位置 */
  restoreScroll: () => void;
  /** 绑定到滚动容器（默认 window） */
  containerRef: React.RefObject<HTMLElement>;
}

export function useScrollRestore(
  key: string,
  options: UseScrollRestoreOptions = {},
): UseScrollRestoreReturn {
  const { persist = true, delay = 100, behavior = "auto" } = options;
  const containerRef = useRef<HTMLElement>(null);
  const memoryStore = useRef<Record<string, number>>({});

  const getScrollTop = useCallback((): number => {
    if (containerRef.current) {
      return containerRef.current.scrollTop;
    }
    return window.scrollY || document.documentElement.scrollTop;
  }, []);

  const saveScroll = useCallback(() => {
    const top = getScrollTop();
    memoryStore.current[key] = top;

    if (persist) {
      try {
        sessionStorage.setItem(STORAGE_PREFIX + key, String(top));
      } catch {
        // 静默失败
      }
    }
  }, [key, persist, getScrollTop]);

  const restoreScroll = useCallback(() => {
    setTimeout(() => {
      let top = memoryStore.current[key];

      if (top === undefined && persist) {
        try {
          const stored = sessionStorage.getItem(STORAGE_PREFIX + key);
          top = stored ? parseInt(stored, 10) : 0;
        } catch {
          top = 0;
        }
      }

      if (top === undefined) top = 0;

      if (containerRef.current) {
        containerRef.current.scrollTo({ top, behavior });
      } else {
        window.scrollTo({ top, behavior });
      }
    }, delay);
  }, [key, persist, delay, behavior]);

  // 组件卸载时自动保存
  useEffect(() => {
    return () => saveScroll();
  }, [saveScroll]);

  return { saveScroll, restoreScroll, containerRef };
}

/**
 * 路由切换后滚动到顶部。
 */
export function useScrollToTop(
  dependency: any,
  options: { behavior?: ScrollBehavior; delay?: number } = {},
): void {
  const { behavior = "smooth", delay = 0 } = options;

  useEffect(() => {
    setTimeout(() => {
      window.scrollTo({ top: 0, behavior });
    }, delay);
  }, [dependency, behavior, delay]);
}

export default useScrollRestore;
