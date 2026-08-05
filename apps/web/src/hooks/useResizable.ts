/**
 * 拖拽调整大小 Hook（零依赖）。
 *
 * 功能：
 * - useResizable：拖拽边缘调整元素尺寸
 * - 支持 8 个方向手柄
 * - 最小/最大尺寸限制
 * - 保持宽高比
 *
 * 用法：
 *   const { ref, size, handleProps, isResizing } = useResizable({
 *     initialWidth: 400,
 *     initialHeight: 300,
 *     minWidth: 200,
 *   });
 *   <div ref={ref} style={{ width: size.width, height: size.height }}>
 *     <div {...handleProps("se")} className="handle-se" />
 *   </div>
 */

import { useCallback, useRef, useState } from "react";

type HandleDirection = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

interface UseResizableOptions {
  initialWidth?: number;
  initialHeight?: number;
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  /** 保持宽高比 */
  aspectRatio?: number;
  /** 调整回调 */
  onResize?: (width: number, height: number) => void;
  /** 结束回调 */
  onResizeEnd?: (width: number, height: number) => void;
}

interface Size {
  width: number;
  height: number;
}

interface UseResizableReturn {
  ref: React.RefObject<HTMLDivElement | null>;
  size: Size;
  isResizing: boolean;
  /** 获取手柄 props */
  handleProps: (direction: HandleDirection) => {
    onMouseDown: (e: React.MouseEvent) => void;
    style: React.CSSProperties;
  };
  /** 手动设置尺寸 */
  setSize: (size: Partial<Size>) => void;
}

export function useResizable(options: UseResizableOptions = {}): UseResizableReturn {
  const {
    initialWidth = 400,
    initialHeight = 300,
    minWidth = 100,
    minHeight = 100,
    maxWidth = Infinity,
    maxHeight = Infinity,
    aspectRatio,
    onResize,
    onResizeEnd,
  } = options;

  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSizeState] = useState<Size>({ width: initialWidth, height: initialHeight });
  const [isResizing, setIsResizing] = useState(false);

  const startRef = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const dirRef = useRef<HandleDirection>("se");

  const clamp = useCallback(
    (w: number, h: number): Size => {
      let width = Math.max(minWidth, Math.min(maxWidth, w));
      let height = Math.max(minHeight, Math.min(maxHeight, h));

      if (aspectRatio) {
        height = width / aspectRatio;
        if (height < minHeight) {
          height = minHeight;
          width = height * aspectRatio;
        }
        if (height > maxHeight) {
          height = maxHeight;
          width = height * aspectRatio;
        }
      }

      return { width: Math.round(width), height: Math.round(height) };
    },
    [minWidth, minHeight, maxWidth, maxHeight, aspectRatio],
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      const { x, y, w, h } = startRef.current;
      const dx = e.clientX - x;
      const dy = e.clientY - y;
      const dir = dirRef.current;

      let newW = w;
      let newH = h;

      if (dir.includes("e")) newW = w + dx;
      if (dir.includes("w")) newW = w - dx;
      if (dir.includes("s")) newH = h + dy;
      if (dir.includes("n")) newH = h - dy;

      const clamped = clamp(newW, newH);
      setSizeState(clamped);
      onResize?.(clamped.width, clamped.height);
    },
    [clamp, onResize],
  );

  const handleMouseUp = useCallback(() => {
    setIsResizing(false);
    document.removeEventListener("mousemove", handleMouseMove);
    document.removeEventListener("mouseup", handleMouseUp);
    onResizeEnd?.(size.width, size.height);
  }, [handleMouseMove, onResizeEnd, size]);

  const handleProps = useCallback(
    (direction: HandleDirection) => ({
      onMouseDown: (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        dirRef.current = direction;
        startRef.current = { x: e.clientX, y: e.clientY, w: size.width, h: size.height };
        setIsResizing(true);
        document.addEventListener("mousemove", handleMouseMove);
        document.addEventListener("mouseup", handleMouseUp);
      },
      style: { cursor: getCursor(direction) } as React.CSSProperties,
    }),
    [size, handleMouseMove, handleMouseUp],
  );

  const setSize = useCallback(
    (partial: Partial<Size>) => {
      setSizeState((prev) => {
        const next = { ...prev, ...partial };
        return clamp(next.width, next.height);
      });
    },
    [clamp],
  );

  return { ref, size, isResizing, handleProps, setSize };
}

function getCursor(dir: HandleDirection): string {
  const map: Record<HandleDirection, string> = {
    n: "ns-resize",
    s: "ns-resize",
    e: "ew-resize",
    w: "ew-resize",
    ne: "nesw-resize",
    sw: "nesw-resize",
    nw: "nwse-resize",
    se: "nwse-resize",
  };
  return map[dir];
}

export default useResizable;
