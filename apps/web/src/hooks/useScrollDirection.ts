/**
 * 滚动方向 Hook（零依赖）。
 *
 * 功能：
 * - useScrollDirection：检测滚动方向（上/下）
 * - 滚动速度
 * - 是否滚动中
 *
 * 用法：
 *   const { direction, isScrolling, velocity } = useScrollDirection();
 *   // direction: "up" | "down" | null
 */

import { useCallback, useEffect, useRef, useState } from "react";

type ScrollDirection = "up" | "down" | null;

interface UseScrollDirectionOptions {
  /** 最小触发距离（px，默认 10） */
  threshold?: number;
  /** 滚动结束判定时间（ms，默认 150） */
  scrollEndDelay?: number;
  /** 目标元素（不传则监听 window） */
  targetRef?: React.RefObject<HTMLElement | null>;
}

interface UseScrollDirectionReturn {
  /** 滚动方向 */
  direction: ScrollDirection;
  /** 是否滚动中 */
  isScrolling: boolean;
  /** 滚动速度（px/s） */
  velocity: number;
  /** 当前滚动位置 */
  scrollY: number;
}

export function useScrollDirection(options: UseScrollDirectionOptions = {}): UseScrollDirectionReturn {
  const { threshold = 10, scrollEndDelay = 150, targetRef } = options;

  const [direction, setDirection] = useState<ScrollDirection>(null);
  const [isScrolling, setIsScrolling] = useState(false);
  const [velocity, setVelocity] = useState(0);
  const [scrollY, setScrollY] = useState(0);

  const lastYRef = useRef(0);
  const lastTimeRef = useRef(Date.now());
  const endTimerRef = useRef<number>(0);

  const handleScroll = useCallback(() => {
    const target = targetRef?.current;
    const currentY = target ? target.scrollTop : window.scrollY;
    const now = Date.now();

    const delta = currentY - lastYRef.current;
    const timeDelta = (now - lastTimeRef.current) / 1000;

    setScrollY(currentY);
    setIsScrolling(true);

    // 方向判定
    if (Math.abs(delta) >= threshold) {
      setDirection(delta > 0 ? "down" : "up");
      setVelocity(timeDelta > 0 ? Math.abs(delta / timeDelta) : 0);
    }

    lastYRef.current = currentY;
    lastTimeRef.current = now;

    // 滚动结束
    clearTimeout(endTimerRef.current);
    endTimerRef.current = window.setTimeout(() => {
      setIsScrolling(false);
      setVelocity(0);
    }, scrollEndDelay);
  }, [threshold, scrollEndDelay, targetRef]);

  useEffect(() => {
    const target = targetRef?.current || window;
    target.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      target.removeEventListener("scroll", handleScroll);
      clearTimeout(endTimerRef.current);
    };
  }, [handleScroll, targetRef]);

  return { direction, isScrolling, velocity, scrollY };
}

export default useScrollDirection;
