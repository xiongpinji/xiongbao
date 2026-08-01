/**
 * 元素悬停 Hook（零依赖）。
 *
 * 功能：
 * - useHover：检测鼠标悬停状态
 * - 悬停延迟（防止闪烁）
 * - 悬停坐标
 *
 * 用法：
 *   const { ref, isHovered } = useHover();
 *   <div ref={ref}>{isHovered ? "悬停中" : "移入试试"}</div>
 */

import { useCallback, useRef, useState } from "react";

interface UseHoverOptions {
  /** 进入延迟（ms，默认 0） */
  enterDelay?: number;
  /** 离开延迟（ms，默认 0） */
  leaveDelay?: number;
  /** 悬停变化回调 */
  onChange?: (hovered: boolean) => void;
  /** 是否禁用 */
  disabled?: boolean;
}

interface UseHoverReturn {
  /** 绑定到元素 */
  ref: React.RefObject<HTMLElement | null>;
  /** 是否悬停 */
  isHovered: boolean;
  /** 悬停坐标（相对元素） */
  position: { x: number; y: number };
  /** 手动设置（用于外部控制） */
  setHovered: (value: boolean) => void;
}

export function useHover(options: UseHoverOptions = {}): UseHoverReturn {
  const { enterDelay = 0, leaveDelay = 0, onChange, disabled = false } = options;

  const [isHovered, setIsHovered] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  const ref = useRef<HTMLElement | null>(null);
  const enterTimerRef = useRef<number>(0);
  const leaveTimerRef = useRef<number>(0);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const setHovered = useCallback(
    (value: boolean) => {
      if (disabled) return;
      clearTimeout(enterTimerRef.current);
      clearTimeout(leaveTimerRef.current);

      if (value && enterDelay > 0) {
        enterTimerRef.current = window.setTimeout(() => {
          setIsHovered(true);
          onChangeRef.current?.(true);
        }, enterDelay);
      } else if (!value && leaveDelay > 0) {
        leaveTimerRef.current = window.setTimeout(() => {
          setIsHovered(false);
          onChangeRef.current?.(false);
        }, leaveDelay);
      } else {
        setIsHovered(value);
        onChangeRef.current?.(value);
      }
    },
    [disabled, enterDelay, leaveDelay],
  );

  // 通过回调 ref 绑定事件
  const setRef = useCallback(
    (el: HTMLElement | null) => {
      // 清理旧元素事件
      if (ref.current) {
        ref.current.removeEventListener("mouseenter", handleEnter);
        ref.current.removeEventListener("mouseleave", handleLeave);
        ref.current.removeEventListener("mousemove", handleMove);
      }

      ref.current = el;

      if (el && !disabled) {
        el.addEventListener("mouseenter", handleEnter);
        el.addEventListener("mouseleave", handleLeave);
        el.addEventListener("mousemove", handleMove);
      }
    },
    [disabled],
  );

  const handleEnter = () => setHovered(true);
  const handleLeave = () => {
    setHovered(false);
    setPosition({ x: 0, y: 0 });
  };
  const handleMove = (e: MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setPosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  return {
    ref: { current: ref.current } as React.RefObject<HTMLElement | null>,
    isHovered,
    position,
    setHovered,
  };
}

export default useHover;
