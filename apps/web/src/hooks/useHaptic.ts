/**
 * 触觉反馈 Hook（零依赖）。
 *
 * 功能：
 * - useHaptic：Vibration API 触觉反馈
 * - 预设模式（轻触/成功/错误/警告）
 * - 自定义振动模式
 * - 设备支持检测
 *
 * 用法：
 *   const { vibrate, isSupported } = useHaptic();
 *   <button onClick={() => vibrate("success")}>提交</button>
 */

import { useCallback, useMemo } from "react";

type HapticPattern = "light" | "medium" | "heavy" | "success" | "error" | "warning" | "selection";

interface UseHapticOptions {
  /** 是否启用（默认 true） */
  enabled?: boolean;
  /** 自定义模式映射 */
  customPatterns?: Record<string, number | number[]>;
}

interface UseHapticReturn {
  /** 触发振动 */
  vibrate: (pattern?: HapticPattern | number | number[]) => void;
  /** 是否支持 Vibration API */
  isSupported: boolean;
  /** 停止振动 */
  stop: () => void;
}

// 预设振动模式（ms）
const PATTERNS: Record<HapticPattern, number | number[]> = {
  light: 10,
  medium: 20,
  heavy: 40,
  success: [10, 50, 10],
  error: [50, 30, 50, 30, 50],
  warning: [30, 30, 30],
  selection: 5,
};

export function useHaptic(options: UseHapticOptions = {}): UseHapticReturn {
  const { enabled = true, customPatterns } = options;

  const isSupported = useMemo(() => {
    if (typeof navigator === "undefined") return false;
    return "vibrate" in navigator;
  }, []);

  const vibrate = useCallback(
    (pattern: HapticPattern | number | number[] = "light") => {
      if (!enabled || !isSupported) return;

      let value: number | number[];

      if (typeof pattern === "string") {
        // 先查自定义，再查预设
        value = customPatterns?.[pattern] ?? PATTERNS[pattern] ?? PATTERNS.light;
      } else {
        value = pattern;
      }

      try {
        navigator.vibrate(value);
      } catch {
        // 静默失败
      }
    },
    [enabled, isSupported, customPatterns],
  );

  const stop = useCallback(() => {
    if (!isSupported) return;
    try {
      navigator.vibrate(0);
    } catch {
      // 静默失败
    }
  }, [isSupported]);

  return { vibrate, isSupported, stop };
}

export default useHaptic;
