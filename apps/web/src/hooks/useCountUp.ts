/**
 * 数字动画 Hook（零依赖）。
 *
 * 功能：
 * - useCountUp：数字从 0 动画递增到目标值
 * - 支持缓动函数
 * - 格式化输出（千分位/小数）
 *
 * 用法：
 *   const { display, start } = useCountUp(12345, { duration: 2000, decimals: 0 });
 *   <span>{display}</span>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseCountUpOptions {
  /** 动画时长（ms，默认 1500） */
  duration?: number;
  /** 小数位数（默认 0） */
  decimals?: number;
  /** 是否自动开始（默认 true） */
  autoStart?: boolean;
  /** 千分位分隔（默认 true） */
  separator?: boolean;
  /** 前缀 */
  prefix?: string;
  /** 后缀 */
  suffix?: string;
  /** 完成回调 */
  onComplete?: () => void;
}

interface UseCountUpReturn {
  /** 格式化显示值 */
  display: string;
  /** 当前原始数值 */
  value: number;
  /** 是否动画中 */
  isAnimating: boolean;
  /** 开始/重新开始 */
  start: () => void;
  /** 重置为 0 */
  reset: () => void;
}

// easeOutExpo 缓动
function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

function formatNumber(
  value: number,
  decimals: number,
  separator: boolean,
  prefix: string,
  suffix: string,
): string {
  let str = value.toFixed(decimals);
  if (separator) {
    const parts = str.split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    str = parts.join(".");
  }
  return `${prefix}${str}${suffix}`;
}

export function useCountUp(
  target: number,
  options: UseCountUpOptions = {},
): UseCountUpReturn {
  const {
    duration = 1500,
    decimals = 0,
    autoStart = true,
    separator = true,
    prefix = "",
    suffix = "",
    onComplete,
  } = options;

  const [value, setValue] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const rafRef = useRef<number>(0);
  const startTimeRef = useRef(0);

  const animate = useCallback(() => {
    setIsAnimating(true);
    startTimeRef.current = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOutExpo(progress);
      const current = eased * target;

      setValue(current);

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setValue(target);
        setIsAnimating(false);
        onComplete?.();
      }
    };

    rafRef.current = requestAnimationFrame(tick);
  }, [target, duration, onComplete]);

  const start = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    setValue(0);
    animate();
  }, [animate]);

  const reset = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    setValue(0);
    setIsAnimating(false);
  }, []);

  useEffect(() => {
    if (autoStart) animate();
    return () => cancelAnimationFrame(rafRef.current);
  }, [autoStart, animate]);

  const display = formatNumber(value, decimals, separator, prefix, suffix);

  return { display, value, isAnimating, start, reset };
}

export default useCountUp;
