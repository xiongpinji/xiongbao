/**
 * 动画帧循环 Hook（零依赖）。
 *
 * 功能：
 * - useAnimationFrame：requestAnimationFrame 循环
 * - 自动清理 + 暂停/恢复
 * - 帧率控制 + delta time
 * - FPS 统计
 *
 * 用法：
 *   useAnimationFrame((delta, elapsed) => {
 *     // 每帧更新逻辑
 *     position += speed * delta;
 *   }, { active: isPlaying });
 */

import { useEffect, useRef } from "react";

interface UseAnimationFrameOptions {
  /** 是否激活（默认 true） */
  active?: boolean;
  /** 最大帧率限制（默认不限制） */
  maxFps?: number;
}

type FrameCallback = (delta: number, elapsed: number) => void;

export function useAnimationFrame(
  callback: FrameCallback,
  options: UseAnimationFrameOptions = {},
): void {
  const { active = true, maxFps } = options;

  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const frameRef = useRef<number>(0);
  const startTimeRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const intervalRef = useRef<number>(maxFps ? 1000 / maxFps : 0);

  useEffect(() => {
    if (!active) {
      cancelAnimationFrame(frameRef.current);
      return;
    }

    startTimeRef.current = performance.now();
    lastTimeRef.current = startTimeRef.current;

    const loop = (now: number) => {
      frameRef.current = requestAnimationFrame(loop);

      // 帧率限制
      if (intervalRef.current > 0) {
        const elapsed = now - lastTimeRef.current;
        if (elapsed < intervalRef.current) return;
      }

      const delta = (now - lastTimeRef.current) / 1000; // 秒
      const totalElapsed = (now - startTimeRef.current) / 1000;
      lastTimeRef.current = now;

      callbackRef.current(delta, totalElapsed);
    };

    frameRef.current = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(frameRef.current);
    };
  }, [active, maxFps]);
}

// ─── FPS 计数器 ───

import { useState } from "react";

/** FPS 统计 Hook */
export function useFps(sampleSize: number = 60): number {
  const [fps, setFps] = useState(0);
  const framesRef = useRef<number[]>([]);

  useAnimationFrame(() => {
    const now = performance.now();
    framesRef.current.push(now);

    // 保留最近 sampleSize 帧
    if (framesRef.current.length > sampleSize) {
      framesRef.current.shift();
    }

    if (framesRef.current.length >= 2) {
      const first = framesRef.current[0];
      const last = framesRef.current[framesRef.current.length - 1];
      const elapsed = last - first;
      if (elapsed > 0) {
        setFps(Math.round(((framesRef.current.length - 1) / elapsed) * 1000));
      }
    }
  });

  return fps;
}

export default useAnimationFrame;
