/**
 * 视差滚动 Hook（零依赖）。
 *
 * 功能：
 * - useParallax：元素随滚动产生视差位移
 * - 支持速度系数（正/负方向）
 * - 支持水平/垂直方向
 * - requestAnimationFrame 节流
 *
 * 用法：
 *   const { ref, offset } = useParallax({ speed: 0.5 });
 *   <div ref={ref} style={{ transform: `translateY(${offset}px)` }} />
 */

import { useEffect, useRef, useState } from "react";

interface UseParallaxOptions {
  /** 速度系数（0=静止, 1=同步, >1=加速, 负=反向，默认 0.5） */
  speed?: number;
  /** 方向（默认 vertical） */
  axis?: "vertical" | "horizontal";
  /** 是否禁用（默认 false） */
  disabled?: boolean;
  /** 最大偏移限制（px，默认无限制） */
  maxOffset?: number;
}

interface UseParallaxReturn {
  /** 绑定到目标元素 */
  ref: React.RefObject<HTMLElement | null>;
  /** 当前偏移量（px） */
  offset: number;
  /** 进度 0-1（元素在视口中的位置） */
  progress: number;
}

export function useParallax(options: UseParallaxOptions = {}): UseParallaxReturn {
  const { speed = 0.5, axis = "vertical", disabled = false, maxOffset } = options;

  const ref = useRef<HTMLElement | null>(null);
  const [offset, setOffset] = useState(0);
  const [progress, setProgress] = useState(0);
  const tickingRef = useRef(false);

  useEffect(() => {
    if (disabled || typeof window === "undefined") return;

    const update = () => {
      const el = ref.current;
      if (!el) {
        tickingRef.current = false;
        return;
      }

      const rect = el.getBoundingClientRect();
      const viewportSize = axis === "vertical" ? window.innerHeight : window.innerWidth;
      const elementCenter = axis === "vertical"
        ? rect.top + rect.height / 2
        : rect.left + rect.width / 2;

      // 元素中心相对视口中心的偏移
      const delta = elementCenter - viewportSize / 2;
      // 进度：0（顶部进入）→ 1（底部离开）
      const p = Math.max(0, Math.min(1, 1 - (rect.top + rect.height) / (viewportSize + rect.height)));

      let newOffset = delta * speed * -1;

      // 限制最大偏移
      if (maxOffset !== undefined) {
        newOffset = Math.max(-maxOffset, Math.min(maxOffset, newOffset));
      }

      setOffset(Math.round(newOffset * 100) / 100);
      setProgress(p);
      tickingRef.current = false;
    };

    const onScroll = () => {
      if (!tickingRef.current) {
        tickingRef.current = true;
        requestAnimationFrame(update);
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });

    // 初始计算
    update();

    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [speed, axis, disabled, maxOffset]);

  return { ref, offset, progress };
}

export default useParallax;
