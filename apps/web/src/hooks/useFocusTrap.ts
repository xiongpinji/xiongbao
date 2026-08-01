/**
 * 焦点陷阱 Hook（零依赖，无障碍）。
 *
 * 功能：
 * - useFocusTrap：模态框/抽屉内焦点循环
 * - Tab / Shift+Tab 在容器内循环
 * - 打开时自动聚焦首个元素
 * - 关闭时恢复之前焦点
 *
 * 用法：
 *   const { containerRef } = useFocusTrap(isOpen);
 *   <div ref={containerRef}>模态框内容</div>
 */

import { useCallback, useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
  "[contenteditable]",
].join(", ");

interface UseFocusTrapOptions {
  /** 初始焦点选择器（默认首个可聚焦元素） */
  initialFocus?: string;
  /** 关闭时恢复焦点（默认 true） */
  restoreFocus?: boolean;
}

interface UseFocusTrapReturn {
  /** 绑定到容器 */
  containerRef: React.RefObject<HTMLElement>;
}

export function useFocusTrap(
  active: boolean,
  options: UseFocusTrapOptions = {},
): UseFocusTrapReturn {
  const { initialFocus, restoreFocus = true } = options;
  const containerRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active || !containerRef.current) return;

    const container = containerRef.current;

    // 保存之前的焦点
    previousFocusRef.current = document.activeElement as HTMLElement;

    // 聚焦首个元素
    const focusFirst = () => {
      if (initialFocus) {
        const el = container.querySelector<HTMLElement>(initialFocus);
        if (el) {
          el.focus();
          return;
        }
      }
      const focusable = container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (focusable.length > 0) {
        focusable[0].focus();
      } else {
        container.focus();
      }
    };

    // 延迟一帧确保 DOM 渲染完成
    requestAnimationFrame(focusFirst);

    // Tab 键循环
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;

      const focusable = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => el.offsetParent !== null); // 排除隐藏元素

      if (focusable.length === 0) {
        e.preventDefault();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const current = document.activeElement;

      if (e.shiftKey) {
        // Shift+Tab：从第一个跳到最后一个
        if (current === first || !container.contains(current)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        // Tab：从最后一个跳到第一个
        if (current === last || !container.contains(current)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    container.addEventListener("keydown", handleKeyDown);

    return () => {
      container.removeEventListener("keydown", handleKeyDown);

      // 恢复焦点
      if (restoreFocus && previousFocusRef.current) {
        previousFocusRef.current.focus();
      }
    };
  }, [active, initialFocus, restoreFocus]);

  return { containerRef };
}

export default useFocusTrap;
