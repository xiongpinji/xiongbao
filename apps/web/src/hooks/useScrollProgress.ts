/**
 * 滚动进度 Hook（零依赖）。
 *
 * 功能：
 * - useScrollProgress：页面/容器滚动进度百分比
 * - 阅读进度条
 * - 方向检测（上/下）
 *
 * 用法：
 *   const { progress, direction } = useScrollProgress();
 *   <div style={{ width: `${progress * 100}%` }} className="progress-bar" />
 */

import { useEffect, useRef, useState } from "react";

interface UseScrollProgressOptions {
  /** 目标容器 ref（不传则监听 window） */
  containerRef?: React.RefObject<HTMLElement | null>;
  /** 节流间隔（ms，默认 16 ≈ 60fps） */
  throttleMs?: number;
}

interface UseScrollProgressReturn {
  /** 进度 0-1 */
  progress: number;
  /** 百分比字符串（如 "45%"） */
  percentage: string;
  /** 滚动方向 */
  direction: "up" | "down" | "idle";
  /** 是否已到底部 */
  isAtBottom: boolean;
  /** 是否已滚动（progress > 0） */
  hasScrolled: boolean;
  /** 已滚动像素 */
  scrollY: number;
}

export function useScrollProgress(
  options: UseScrollProgressOptions = {},
): UseScrollProgressReturn {
  const { containerRef, throttleMs = 16 } = options;

  const [progress, setProgress] = useState(0);
  const [direction, setDirection] = useState<"up" | "down" | "idle">("idle");
  const [scrollY, setScrollY] = useState(0);

  const lastScrollRef = useRef(0);
  const tickingRef = useRef(false);
  const lastTimeRef = useRef(0);

  useEffect(() => {
    const getTarget = () => containerRef?.current ?? null;

    const update = () => {
      const el = getTarget();
      let currentScroll: number;
      let maxScroll: number;

      if (el) {
        currentScroll = el.scrollTop;
        maxScroll = el.scrollHeight - el.clientHeight;
      } else {
        currentScroll = window.scrollY || document.documentElement.scrollTop;
        maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      }

      const p = maxScroll > 0 ? Math.min(currentScroll / maxScroll, 1) : 0;

      setProgress(p);
      setScrollY(currentScroll);
      setDirection(currentScroll > lastScrollRef.current ? "down" : currentScroll < lastScrollRef.current ? "up" : "idle");
      lastScrollRef.current = currentScroll;
      tickingRef.current = false;
    };

    const onScroll = () => {
      const now = Date.now();
      if (now - lastTimeRef.current < throttleMs) return;
      lastTimeRef.current = now;

      if (!tickingRef.current) {
        tickingRef.current = true;
        requestAnimationFrame(update);
      }
    };

    const target = getTarget();
    if (target) {
      target.addEventListener("scroll", onScroll, { passive: true });
    } else {
      window.addEventListener("scroll", onScroll, { passive: true });
    }

    // 初始化
    update();

    return () => {
      if (target) {
        target.removeEventListener("scroll", onScroll);
      } else {
        window.removeEventListener("scroll", onScroll);
      }
    };
  }, [containerRef, throttleMs]);

  const isAtBottom = progress >= 0.99;
  const hasScrolled = progress > 0;
  const percentage = `${Math.round(progress * 100)}%`;

  return { progress, percentage, direction, isAtBottom, hasScrolled, scrollY };
}

export default useScrollProgress;
