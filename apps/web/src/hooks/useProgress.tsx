/**
 * 进度条 Hook + 组件（零依赖）。
 *
 * 功能：
 * - useProgress：管理进度状态（确定/不确定）
 * - ProgressBar：顶部细线进度条（类 NProgress）
 * - 支持模拟进度（异步操作无真实进度时）
 *
 * 用法：
 *   const { progress, start, done, ProgressBar } = useProgress();
 *   start();           // 开始（不确定模式）
 *   setProgress(60);   // 设置确定进度
 *   done();            // 完成（快速到 100% 后隐藏）
 *   <ProgressBar />
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseProgressReturn {
  /** 当前进度 0-100 */
  progress: number;
  /** 是否活跃 */
  isActive: boolean;
  /** 开始（不确定模式，自动递增） */
  start: () => void;
  /** 设置确定进度 */
  setProgress: (value: number) => void;
  /** 递增进度 */
  increment: (amount?: number) => void;
  /** 完成 */
  done: () => void;
  /** 重置 */
  reset: () => void;
  /** 进度条组件 */
  ProgressBar: () => JSX.Element | null;
}

export function useProgress(): UseProgressReturn {
  const [progress, setProgressState] = useState(0);
  const [isActive, setIsActive] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const start = useCallback(() => {
    clearTimers();
    setProgressState(5);
    setIsActive(true);

    // 模拟进度递增（越来越慢）
    timerRef.current = setInterval(() => {
      setProgressState((prev) => {
        if (prev >= 90) return prev;
        // 越接近 90 增量越小
        const remaining = 90 - prev;
        const inc = Math.max(0.5, remaining * 0.08);
        return Math.min(90, prev + inc);
      });
    }, 200);
  }, [clearTimers]);

  const setProgress = useCallback(
    (value: number) => {
      clearTimers();
      const clamped = Math.max(0, Math.min(100, value));
      setProgressState(clamped);
      setIsActive(true);

      if (clamped >= 100) {
        hideTimerRef.current = setTimeout(() => {
          setIsActive(false);
          setProgressState(0);
        }, 400);
      }
    },
    [clearTimers],
  );

  const increment = useCallback((amount?: number) => {
    setProgressState((prev) => {
      const inc = amount ?? Math.max(1, (100 - prev) * 0.1);
      return Math.min(99, prev + inc);
    });
  }, []);

  const done = useCallback(() => {
    clearTimers();
    setProgressState(100);
    hideTimerRef.current = setTimeout(() => {
      setIsActive(false);
      setProgressState(0);
    }, 400);
  }, [clearTimers]);

  const reset = useCallback(() => {
    clearTimers();
    setProgressState(0);
    setIsActive(false);
  }, [clearTimers]);

  // 清理
  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  const ProgressBar = useCallback(() => {
    if (!isActive && progress === 0) return null;

    return (
      <div
        className="fixed left-0 top-0 z-[9999] w-full"
        style={{ pointerEvents: "none" }}
      >
        {/* 主进度条 */}
        <div
          className="h-[2px] bg-[#d6ad62] transition-all duration-300 ease-out"
          style={{
            width: `${progress}%`,
            opacity: isActive || progress > 0 ? 1 : 0,
            boxShadow: "0 0 8px rgba(214, 173, 98, 0.6)",
          }}
        />
        {/* 前端光点 */}
        {isActive && progress < 100 && (
          <div
            className="absolute right-0 top-0 h-[2px] w-[80px] bg-gradient-to-r from-transparent to-[#d6ad62]"
            style={{
              right: `${100 - progress}%`,
              opacity: 0.8,
            }}
          />
        )}
      </div>
    );
  }, [isActive, progress]);

  return { progress, isActive, start, setProgress, increment, done, reset, ProgressBar };
}

export default useProgress;
