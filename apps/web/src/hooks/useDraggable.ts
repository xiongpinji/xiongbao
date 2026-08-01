/**
 * 元素拖拽移动 Hook（零依赖）。
 *
 * 功能：
 * - useDraggable：使元素可拖拽移动
 * - 支持边界限制
 * - 拖拽手柄
 * - 惯性/吸附
 *
 * 用法：
 *   const { ref, handleRef, position, isDragging } = useDraggable();
 *   <div ref={ref}><div ref={handleRef}>拖我</div></div>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseDraggableOptions {
  /** 初始位置 */
  initialPosition?: { x: number; y: number };
  /** 边界容器 ref（不传则无限制） */
  boundsRef?: React.RefObject<HTMLElement | null>;
  /** 吸附网格大小（px，0=不吸附） */
  snapGrid?: number;
  /** 是否禁用 */
  disabled?: boolean;
  /** 拖拽开始回调 */
  onDragStart?: (pos: { x: number; y: number }) => void;
  /** 拖拽中回调 */
  onDrag?: (pos: { x: number; y: number }) => void;
  /** 拖拽结束回调 */
  onDragEnd?: (pos: { x: number; y: number }) => void;
}

interface UseDraggableReturn {
  /** 绑定到可拖拽元素 */
  ref: React.RefCallback<HTMLElement>;
  /** 绑定到拖拽手柄（不传则整个元素可拖） */
  handleRef: React.RefCallback<HTMLElement>;
  /** 当前位置 */
  position: { x: number; y: number };
  /** 是否拖拽中 */
  isDragging: boolean;
  /** 手动设置位置 */
  setPosition: (pos: { x: number; y: number }) => void;
  /** 重置到初始位置 */
  reset: () => void;
}

export function useDraggable(options: UseDraggableOptions = {}): UseDraggableReturn {
  const {
    initialPosition = { x: 0, y: 0 },
    boundsRef,
    snapGrid = 0,
    disabled = false,
    onDragStart,
    onDrag,
    onDragEnd,
  } = options;

  const [position, setPositionState] = useState(initialPosition);
  const [isDragging, setIsDragging] = useState(false);

  const elRef = useRef<HTMLElement | null>(null);
  const handleElRef = useRef<HTMLElement | null>(null);
  const dragStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 });
  const callbacksRef = useRef({ onDragStart, onDrag, onDragEnd });
  callbacksRef.current = { onDragStart, onDrag, onDragEnd };

  const clampToBounds = useCallback(
    (x: number, y: number): { x: number; y: number } => {
      const bounds = boundsRef?.current;
      const el = elRef.current;
      if (!bounds || !el) return { x, y };

      const bRect = bounds.getBoundingClientRect();
      const eRect = el.getBoundingClientRect();
      const maxX = bRect.width - eRect.width;
      const maxY = bRect.height - eRect.height;

      return {
        x: Math.max(0, Math.min(x, maxX)),
        y: Math.max(0, Math.min(y, maxY)),
      };
    },
    [boundsRef],
  );

  const applySnap = useCallback(
    (val: number): number => {
      if (snapGrid <= 0) return val;
      return Math.round(val / snapGrid) * snapGrid;
    },
    [snapGrid],
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      const { x: startX, y: startY, posX, posY } = dragStartRef.current;
      let newX = posX + (e.clientX - startX);
      let newY = posY + (e.clientY - startY);

      newX = applySnap(newX);
      newY = applySnap(newY);

      const clamped = clampToBounds(newX, newY);
      setPositionState(clamped);
      callbacksRef.current.onDrag?.(clamped);
    },
    [applySnap, clampToBounds],
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
    document.removeEventListener("mousemove", handleMouseMove);
    document.removeEventListener("mouseup", handleMouseUp);
    callbacksRef.current.onDragEnd?.(position);
  }, [handleMouseMove, position]);

  const handleMouseDown = useCallback(
    (e: MouseEvent) => {
      if (disabled) return;
      e.preventDefault();
      dragStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        posX: position.x,
        posY: position.y,
      };
      setIsDragging(true);
      callbacksRef.current.onDragStart?.(position);
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    [disabled, position, handleMouseMove, handleMouseUp],
  );

  const ref = useCallback(
    (el: HTMLElement | null) => {
      // 清理旧绑定
      if (elRef.current && !handleElRef.current) {
        elRef.current.removeEventListener("mousedown", handleMouseDown as EventListener);
      }
      elRef.current = el;
      if (el && !handleElRef.current && !disabled) {
        el.addEventListener("mousedown", handleMouseDown as EventListener);
      }
    },
    [handleMouseDown, disabled],
  );

  const handleRef = useCallback(
    (el: HTMLElement | null) => {
      if (handleElRef.current) {
        handleElRef.current.removeEventListener("mousedown", handleMouseDown as EventListener);
      }
      handleElRef.current = el;
      if (el && !disabled) {
        el.addEventListener("mousedown", handleMouseDown as EventListener);
      }
    },
    [handleMouseDown, disabled],
  );

  const setPosition = useCallback((pos: { x: number; y: number }) => {
    setPositionState(pos);
  }, []);

  const reset = useCallback(() => {
    setPositionState(initialPosition);
  }, [initialPosition]);

  // 清理
  useEffect(() => {
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  return { ref, handleRef, position, isDragging, setPosition, reset };
}

export default useDraggable;
