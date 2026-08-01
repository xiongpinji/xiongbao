/**
 * 倒计时 Hook（零依赖）。
 *
 * 功能：
 * - useCountdown：精确倒计时
 * - 支持暂停/恢复/重置
 * - 格式化输出
 *
 * 用法：
 *   const { remaining, formatted, isRunning, start, pause, reset } = useCountdown(60);
 *   <span>{formatted}</span>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseCountdownOptions {
  /** 是否自动开始 */
  autoStart?: boolean;
  /** 倒计时结束回调 */
  onComplete?: () => void;
  /** 每秒 tick 回调 */
  onTick?: (remaining: number) => void;
  /** 计时间隔（ms，默认 1000） */
  interval?: number;
}

interface UseCountdownReturn {
  /** 剩余秒数 */
  remaining: number;
  /** 格式化字符串 HH:MM:SS */
  formatted: string;
  /** 是否运行中 */
  isRunning: boolean;
  /** 是否已完成 */
  isComplete: boolean;
  /** 开始/恢复 */
  start: () => void;
  /** 暂停 */
  pause: () => void;
  /** 重置 */
  reset: (seconds?: number) => void;
  /** 进度（0-1） */
  progress: number;
}

function formatTime(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (h > 0) return `${pad(h)}:${pad(m)}:${pad(s)}`;
  return `${pad(m)}:${pad(s)}`;
}

export function useCountdown(
  initialSeconds: number,
  options: UseCountdownOptions = {},
): UseCountdownReturn {
  const { autoStart = false, onComplete, onTick, interval = 1000 } = options;

  const [remaining, setRemaining] = useState(initialSeconds);
  const [isRunning, setIsRunning] = useState(autoStart);

  const timerRef = useRef<number>(0);
  const endTimeRef = useRef<number>(0);
  const callbacksRef = useRef({ onComplete, onTick });
  callbacksRef.current = { onComplete, onTick };

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = 0;
    }
  }, []);

  const tick = useCallback(() => {
    const now = Date.now();
    const left = Math.max(0, Math.ceil((endTimeRef.current - now) / 1000));
    setRemaining(left);
    callbacksRef.current.onTick?.(left);

    if (left <= 0) {
      clearTimer();
      setIsRunning(false);
      callbacksRef.current.onComplete?.();
    }
  }, [clearTimer]);

  const start = useCallback(() => {
    if (remaining <= 0) return;
    clearTimer();
    endTimeRef.current = Date.now() + remaining * 1000;
    setIsRunning(true);
    timerRef.current = window.setInterval(tick, interval);
  }, [remaining, clearTimer, tick, interval]);

  const pause = useCallback(() => {
    clearTimer();
    setIsRunning(false);
  }, [clearTimer]);

  const reset = useCallback(
    (seconds?: number) => {
      clearTimer();
      setIsRunning(false);
      setRemaining(seconds ?? initialSeconds);
    },
    [clearTimer, initialSeconds],
  );

  // 自动开始
  useEffect(() => {
    if (autoStart) {
      endTimeRef.current = Date.now() + initialSeconds * 1000;
      timerRef.current = window.setInterval(tick, interval);
    }
    return clearTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const progress = initialSeconds > 0 ? 1 - remaining / initialSeconds : 0;

  return {
    remaining,
    formatted: formatTime(remaining),
    isRunning,
    isComplete: remaining <= 0,
    start,
    pause,
    reset,
    progress,
  };
}

export default useCountdown;
