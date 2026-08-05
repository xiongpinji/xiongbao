/**
 * 步骤向导 Hook（零依赖）。
 *
 * 功能：
 * - useStep：多步骤流程管理
 * - 前进/后退/跳转
 * - 步骤验证
 *
 * 用法：
 *   const { step, next, prev, goTo, isFirst, isLast } = useStep(3);
 */

import { useCallback, useState } from "react";

interface UseStepOptions {
  /** 初始步骤（默认 0） */
  initialStep?: number;
  /** 步骤变化回调 */
  onChange?: (step: number) => void;
  /** 步骤验证（返回 false 阻止前进） */
  validate?: (step: number) => boolean;
}

interface UseStepReturn {
  /** 当前步骤（0-based） */
  step: number;
  /** 下一步 */
  next: () => void;
  /** 上一步 */
  prev: () => void;
  /** 跳转到指定步骤 */
  goTo: (step: number) => void;
  /** 是否第一步 */
  isFirst: boolean;
  /** 是否最后一步 */
  isLast: boolean;
  /** 进度（0-1） */
  progress: number;
  /** 重置 */
  reset: () => void;
}

export function useStep(totalSteps: number, options: UseStepOptions = {}): UseStepReturn {
  const { initialStep = 0, onChange, validate } = options;

  const [step, setStep] = useState(Math.min(initialStep, totalSteps - 1));

  const goTo = useCallback(
    (target: number) => {
      const clamped = Math.max(0, Math.min(target, totalSteps - 1));
      setStep((prev) => {
        if (prev === clamped) return prev;
        onChange?.(clamped);
        return clamped;
      });
    },
    [totalSteps, onChange],
  );

  const next = useCallback(() => {
    setStep((prev) => {
      if (prev >= totalSteps - 1) return prev;
      if (validate && !validate(prev)) return prev;
      const nextStep = prev + 1;
      onChange?.(nextStep);
      return nextStep;
    });
  }, [totalSteps, onChange, validate]);

  const prev = useCallback(() => {
    setStep((prev) => {
      if (prev <= 0) return prev;
      const prevStep = prev - 1;
      onChange?.(prevStep);
      return prevStep;
    });
  }, [onChange]);

  const reset = useCallback(() => {
    setStep(initialStep);
    onChange?.(initialStep);
  }, [initialStep, onChange]);

  return {
    step,
    next,
    prev,
    goTo,
    isFirst: step === 0,
    isLast: step === totalSteps - 1,
    progress: totalSteps > 1 ? step / (totalSteps - 1) : 0,
    reset,
  };
}

export default useStep;
