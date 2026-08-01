/**
 * 元素尺寸监听 Hook（零依赖）。
 *
 * 功能：
 * - useElementSize：ResizeObserver 实时监听元素宽高
 * - 支持 border-box / content-box
 * - 初始值 + 变化回调
 *
 * 用法：
 *   const { ref, width, height } = useElementSize<HTMLDivElement>();
 *   <div ref={ref}>监听我的尺寸</div>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface ElementSize {
  width: number;
  height: number;
}

interface UseElementSizeOptions {
  /** 监听模式（默认 border-box） */
  box?: "border-box" | "content-box";
  /** 尺寸变化回调 */
  onChange?: (size: ElementSize) => void;
}

interface UseElementSizeReturn<T extends HTMLElement> {
  /** 绑定到目标元素 */
  ref: React.RefObject<T>;
  /** 宽度 */
  width: number;
  /** 高度 */
  height: number;
  /** 完整尺寸 */
  size: ElementSize;
}

export function useElementSize<T extends HTMLElement = HTMLElement>(
  options: UseElementSizeOptions = {},
): UseElementSizeReturn<T> {
  const { box = "border-box", onChange } = options;
  const ref = useRef<T>(null);
  const [size, setSize] = useState<ElementSize>({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const rect =
          box === "border-box" ? entry.borderBoxSize?.[0] : entry.contentBoxSize?.[0];

        const newWidth = rect
          ? rect.inlineSize
          : entry.contentRect.width;
        const newHeight = rect
          ? rect.blockSize
          : entry.contentRect.height;

        setSize((prev) => {
          if (prev.width === newWidth && prev.height === newHeight) return prev;
          const newSize = { width: newWidth, height: newHeight };
          onChange?.(newSize);
          return newSize;
        });
      }
    });

    observer.observe(element, { box });

    // 初始尺寸
    const rect = element.getBoundingClientRect();
    setSize({ width: rect.width, height: rect.height });

    return () => observer.disconnect();
  }, [box, onChange]);

  return { ref, width: size.width, height: size.height, size };
}

export default useElementSize;
