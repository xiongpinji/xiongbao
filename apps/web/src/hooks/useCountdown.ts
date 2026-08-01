/**
 * 倒计时 Hook（零依赖）。
 *
 * 功能：
 * - useCountdown：秒级倒计时
 * - 支持暂停 / 恢复 / 重置
 * - 格式化输出（mm:ss / hh:mm:ss）
 * - 结束回调
 *
 * 用法：
 *   const { seconds, formatted, isRunning, start, pause, reset } = useCountdown(60);
 *   <span>{formatted}</span>
 *   <button onClick={start}>开始</button>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseCountdownOptions {
  /** 倒计时结束回调 */
  onComplete?: () => void;
  /** 是否自动开始（默认 false） */
  autoStart?: boolean;
}

interface UseCountdownReturn {
  /** 剩余秒数 */
  seconds: number;
  /** 格式化字符串 (mm:ss) */
  formatted: string;
  /** 是否运行中 */
  isRunning: boolean;
  /** 是否已结束 */
  isComplete: boolean;
  /** 开始 / 恢复 */
  start: () => void;
  /** 暂停 */
  pause: () => void;
  /** 重置到初始值 */
  reset: () => void;
}

function formatTime(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;

  if (h > 0) {
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export function useCountdown(
  initialSeconds: number,
  options: UseCountdownOptions = {},
): UseCountdownReturn {
  const { onComplete, autoStart = false } = options;
  const [seconds, setSeconds] = useState(initialSeconds);
  const [isRunning, setIsRunning] = useState(autoStart);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const clearTimer = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const start = useCallback(() => {
    if (seconds <= 0) return;
    setIsRunning(true);
  }, [seconds]);

  const pause = useCallback(() => {
    setIsRunning(false);
  }, []);

  const reset = useCallback(() => {
    clearTimer();
    setSeconds(initialSeconds);
    setIsRunning(false);
  }, [initialSeconds, clearTimer]);

  useEffect(() => {
    if (!isRunning) {
      clearTimer();
      return;
    }

    intervalRef.current = setInterval(() => {
      setSeconds((prev) => {
        if (prev <= 1) {
          clearTimer();
          setIsRunning(false);
          onCompleteRef.current?.();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return clearTimer;
  }, [isRunning, clearTimer]);

  return {
    seconds,
    formatted: formatTime(seconds),
    isRunning,
    isComplete: seconds === 0,
    start,
    pause,
    reset,
  };
}

export default useCountdown;
