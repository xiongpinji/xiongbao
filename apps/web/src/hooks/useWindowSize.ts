/**
 * 窗口尺寸 Hook（零依赖）。
 *
 * 功能：
 * - useWindowSize：实时监听窗口宽高
 * - 防抖处理
 * - 文档尺寸
 *
 * 用法：
 *   const { width, height, isMobile } = useWindowSize();
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseWindowSizeOptions {
  /** 防抖延迟（ms，默认 150） */
  debounceMs?: number;
  /** 变化回调 */
  onChange?: (size: { width: number; height: number }) => void;
}

interface UseWindowSizeReturn {
  /** 窗口宽度 */
  width: number;
  /** 窗口高度 */
  height: number;
  /** 文档宽度 */
  docWidth: number;
  /** 文档高度 */
  docHeight: number;
  /** 是否移动端（< 768px） */
  isMobile: boolean;
  /** 宽高比 */
  aspectRatio: number;
}

export function useWindowSize(options: UseWindowSizeOptions = {}): UseWindowSizeReturn {
  const { debounceMs = 150, onChange } = options;

  const [size, setSize] = useState({
    width: typeof window !== "undefined" ? window.innerWidth : 1024,
    height: typeof window !== "undefined" ? window.innerHeight : 768,
  });
  const [docSize, setDocSize] = useState({ width: 0, height: 0 });

  const timerRef = useRef<number>(0);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const update = useCallback(() => {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const newSize = { width, height };
    setSize(newSize);
    setDocSize({
      width: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
    });
    onChangeRef.current?.(newSize);
  }, []);

  useEffect(() => {
    const handleResize = () => {
      clearTimeout(timerRef.current);
      if (debounceMs > 0) {
        timerRef.current = window.setTimeout(update, debounceMs);
      } else {
        update();
      }
    };

    // 初始文档尺寸
    setDocSize({
      width: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
    });

    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      clearTimeout(timerRef.current);
    };
  }, [debounceMs, update]);

  return {
    width: size.width,
    height: size.height,
    docWidth: docSize.width,
    docHeight: docSize.height,
    isMobile: size.width < 768,
    aspectRatio: size.height > 0 ? size.width / size.height : 0,
  };
}

export default useWindowSize;
