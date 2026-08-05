/**
 * 平滑滚动 Hook（零依赖）。
 *
 * 功能：
 * - useSmoothScroll：程序化平滑滚动到目标
 * - 支持滚动到元素/位置
 * - 自定义缓动
 * - 滚动完成回调
 *
 * 用法：
 *   const { scrollTo, scrollToTop, isScrolling } = useSmoothScroll();
 *   <button onClick={() => scrollTo("#section-2")}>跳转</button>
 */

import { useCallback, useRef, useState } from "react";

interface UseSmoothScrollOptions {
  /** 动画时长（ms，默认 500） */
  duration?: number;
  /** 偏移量（px，默认 0） */
  offset?: number;
  /** 缓动函数 */
  easing?: (t: number) => number;
  /** 完成回调 */
  onComplete?: () => void;
  /** 容器 ref（不传则滚动 window） */
  containerRef?: React.RefObject<HTMLElement | null>;
}

interface UseSmoothScrollReturn {
  /** 滚动到选择器/元素 */
  scrollTo: (target: string | HTMLElement | number) => void;
  /** 滚动到顶部 */
  scrollToTop: () => void;
  /** 滚动到底部 */
  scrollToBottom: () => void;
  /** 是否滚动中 */
  isScrolling: boolean;
  /** 取消滚动 */
  cancel: () => void;
}

// easeInOutCubic
function defaultEasing(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export function useSmoothScroll(options: UseSmoothScrollOptions = {}): UseSmoothScrollReturn {
  const { duration = 500, offset = 0, easing = defaultEasing, onComplete, containerRef } = options;

  const [isScrolling, setIsScrolling] = useState(false);
  const rafRef = useRef<number>(0);

  const cancel = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    setIsScrolling(false);
  }, []);

  const animateScroll = useCallback(
    (targetY: number) => {
      cancel();
      setIsScrolling(true);

      const container = containerRef?.current;
      const startY = container ? container.scrollTop : window.scrollY;
      const distance = targetY - startY;
      const startTime = performance.now();

      const step = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easedProgress = easing(progress);
        const currentY = startY + distance * easedProgress;

        if (container) {
          container.scrollTop = currentY;
        } else {
          window.scrollTo(0, currentY);
        }

        if (progress < 1) {
          rafRef.current = requestAnimationFrame(step);
        } else {
          setIsScrolling(false);
          onComplete?.();
        }
      };

      rafRef.current = requestAnimationFrame(step);
    },
    [cancel, containerRef, duration, easing, onComplete],
  );

  const scrollTo = useCallback(
    (target: string | HTMLElement | number) => {
      if (typeof target === "number") {
        animateScroll(target);
        return;
      }

      const el = typeof target === "string" ? document.querySelector(target) : target;
      if (!el) return;

      const container = containerRef?.current;
      let targetY: number;

      if (container) {
        const containerRect = container.getBoundingClientRect();
        const elRect = el.getBoundingClientRect();
        targetY = container.scrollTop + elRect.top - containerRect.top + offset;
      } else {
        targetY = el.getBoundingClientRect().top + window.scrollY + offset;
      }

      animateScroll(targetY);
    },
    [animateScroll, containerRef, offset],
  );

  const scrollToTop = useCallback(() => {
    animateScroll(0);
  }, [animateScroll]);

  const scrollToBottom = useCallback(() => {
    const container = containerRef?.current;
    const maxScroll = container
      ? container.scrollHeight - container.clientHeight
      : document.documentElement.scrollHeight - window.innerHeight;
    animateScroll(maxScroll);
  }, [animateScroll, containerRef]);

  return { scrollTo, scrollToTop, scrollToBottom, isScrolling, cancel };
}

export default useSmoothScroll;
