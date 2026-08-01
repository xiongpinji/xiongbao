/**
 * 窗口焦点 Hook（零依赖）。
 *
 * 功能：
 * - useWindowFocus：检测窗口是否获得焦点
 * - 焦点变化回调
 * - 失焦时长统计
 *
 * 用法：
 *   const isFocused = useWindowFocus();
 *   const { isFocused, blurDuration } = useWindowFocus({ trackDuration: true });
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseWindowFocusOptions {
  /** 焦点变化回调 */
  onChange?: (focused: boolean) => void;
  /** 是否追踪失焦时长（默认 false） */
  trackDuration?: boolean;
}

interface UseWindowFocusReturn {
  /** 是否聚焦 */
  isFocused: boolean;
  /** 最近一次失焦持续时长（ms） */
  blurDuration: number;
  /** 累计失焦次数 */
  blurCount: number;
}

export function useWindowFocus(options: UseWindowFocusOptions = {}): UseWindowFocusReturn {
  const { onChange, trackDuration = false } = options;

  const [isFocused, setIsFocused] = useState<boolean>(() => {
    if (typeof document === "undefined") return true;
    return document.hasFocus();
  });
  const [blurDuration, setBlurDuration] = useState(0);
  const [blurCount, setBlurCount] = useState(0);

  const blurStartRef = useRef<number>(0);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const handleFocus = () => {
      setIsFocused(true);
      onChangeRef.current?.(true);

      if (trackDuration && blurStartRef.current > 0) {
        const duration = Date.now() - blurStartRef.current;
        setBlurDuration(duration);
        blurStartRef.current = 0;
      }
    };

    const handleBlur = () => {
      setIsFocused(false);
      onChangeRef.current?.(false);
      setBlurCount((c) => c + 1);

      if (trackDuration) {
        blurStartRef.current = Date.now();
      }
    };

    window.addEventListener("focus", handleFocus);
    window.addEventListener("blur", handleBlur);

    return () => {
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("blur", handleBlur);
    };
  }, [trackDuration]);

  return { isFocused, blurDuration, blurCount };
}

export default useWindowFocus;
