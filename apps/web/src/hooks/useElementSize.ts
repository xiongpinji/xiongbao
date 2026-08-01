/**
 * 元素尺寸监听 Hook（零依赖）。
 *
 * 功能：
 * - useElementSize：实时监听元素宽高变化
 * - 基于 ResizeObserver
 * - 支持 contentRect / borderBox
 *
 * 用法：
 *   const { ref, width, height } = useElementSize();
 *   <div ref={ref}>{width}x{height}</div>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseElementSizeOptions {
  /** 观察模式 */
  box?: "content-box" | "border-box";
  /** 尺寸变化回调 */
  onChange?: (size: { width: number; height: number }) => void;
  /** 是否禁用 */
  disabled?: boolean;
}

interface UseElementSizeReturn {
  /** 绑定到目标元素 */
  ref: React.RefCallback<HTMLElement>;
  /** 宽度 */
  width: number;
  /** 高度 */
  height: number;
  /** 完整尺寸 */
  size: { width: number; height: number };
}

export function useElementSize(options: UseElementSizeOptions = {}): UseElementSizeReturn {
  const { box = "content-box", onChange, disabled = false } = options;

  const [size, setSize] = useState({ width: 0, height: 0 });
  const elRef = useRef<HTMLElement | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const observe = useCallback(
    (el: HTMLElement) => {
      if (disabled || typeof ResizeObserver === "undefined") return;

      observerRef.current = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const rect =
            box === "border-box" ? entry.borderBoxSize?.[0] : entry.contentRect;

          const width = box === "border-box"
            ? (rect as ResizeObserverSize)?.inlineSize ?? entry.contentRect.width
            : entry.contentRect.width;
          const height = box === "border-box"
            ? (rect as ResizeObserverSize)?.blockSize ?? entry.contentRect.height
            : entry.contentRect.height;

          const newSize = { width: Math.round(width), height: Math.round(height) };
          setSize(newSize);
          onChangeRef.current?.(newSize);
        }
      });

      observerRef.current.observe(el, { box });
    },
    [box, disabled],
  );

  const ref = useCallback(
    (el: HTMLElement | null) => {
      // 断开旧观察
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }

      elRef.current = el;
      if (el) {
        // 初始尺寸
        const rect = el.getBoundingClientRect();
        setSize({ width: Math.round(rect.width), height: Math.round(rect.height) });
        observe(el);
      }
    },
    [observe],
  );

  useEffect(() => {
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  return { ref, width: size.width, height: size.height, size };
}

export default useElementSize;
