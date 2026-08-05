/**
 * 鼠标位置 Hook（零依赖）。
 *
 * 功能：
 * - useMousePosition：追踪鼠标坐标
 * - 相对元素位置
 * - 节流控制
 *
 * 用法：
 *   const { x, y, elementX, elementY } = useMousePosition();
 *   const pos = useMousePosition({ throttleMs: 50 });
 */

import { useEffect, useRef, useState } from "react";

interface UseMousePositionOptions {
  /** 节流间隔（ms，默认 16） */
  throttleMs?: number;
  /** 目标元素 ref（不传则追踪全局） */
  targetRef?: React.RefObject<HTMLElement | null>;
  /** 是否启用（默认 true） */
  enabled?: boolean;
}

interface MousePosition {
  /** 页面 X */
  x: number;
  /** 页面 Y */
  y: number;
  /** 视口 X */
  clientX: number;
  /** 视口 Y */
  clientY: number;
  /** 相对元素 X */
  elementX: number;
  /** 相对元素 Y */
  elementY: number;
  /** 是否在元素内 */
  isInside: boolean;
}

const INITIAL: MousePosition = {
  x: 0, y: 0, clientX: 0, clientY: 0, elementX: 0, elementY: 0, isInside: false,
};

export function useMousePosition(
  options: UseMousePositionOptions = {},
): MousePosition {
  const { throttleMs = 16, targetRef, enabled = true } = options;
  const [position, setPosition] = useState<MousePosition>(INITIAL);
  const lastTimeRef = useRef(0);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const handleMove = (e: MouseEvent) => {
      const now = Date.now();
      if (now - lastTimeRef.current < throttleMs) return;
      lastTimeRef.current = now;

      let elementX = 0;
      let elementY = 0;
      let isInside = false;

      const el = targetRef?.current;
      if (el) {
        const rect = el.getBoundingClientRect();
        elementX = e.clientX - rect.left;
        elementY = e.clientY - rect.top;
        isInside = elementX >= 0 && elementY >= 0 && elementX <= rect.width && elementY <= rect.height;
      }

      setPosition({
        x: e.pageX,
        y: e.pageY,
        clientX: e.clientX,
        clientY: e.clientY,
        elementX,
        elementY,
        isInside,
      });
    };

    window.addEventListener("mousemove", handleMove, { passive: true });
    return () => window.removeEventListener("mousemove", handleMove);
  }, [throttleMs, targetRef, enabled]);

  return position;
}

export default useMousePosition;
