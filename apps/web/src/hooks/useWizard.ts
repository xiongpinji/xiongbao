/**
 * 步骤向导 Hook（零依赖）。
 *
 * 功能：
 * - useWizard：多步骤表单/流程导航
 * - 步骤验证 + 条件跳过
 * - 前进/后退/跳转
 * - 进度百分比
 *
 * 用法：
 *   const wizard = useWizard({
 *     steps: ["基本信息", "配置", "确认"],
 *     validateStep: async (step) => step !== 0 || !!name,
 *   });
 *   <StepIndicator current={wizard.current} total={wizard.total} />
 */

import { useCallback, useMemo, useState } from "react";

interface UseWizardOptions {
  /** 步骤名称列表 */
  steps: string[];
  /** 步骤验证（返回 false 阻止前进） */
  validateStep?: (step: number) => boolean | Promise<boolean>;
  /** 完成回调 */
  onComplete?: () => void;
  /** 步骤变化回调 */
  onStepChange?: (step: number) => void;
  /** 初始步骤（默认 0） */
  initialStep?: number;
}

interface UseWizardReturn {
  /** 当前步骤索引 */
  current: number;
  /** 当前步骤名称 */
  currentName: string;
  /** 总步骤数 */
  total: number;
  /** 是否第一步 */
  isFirst: boolean;
  /** 是否最后一步 */
  isLast: boolean;
  /** 进度百分比 (0-100) */
  progress: number;
  /** 下一步 */
  next: () => Promise<void>;
  /** 上一步 */
  prev: () => void;
  /** 跳转到指定步骤 */
  goTo: (step: number) => void;
  /** 是否正在验证 */
  isValidating: boolean;
  /** 已完成的步骤 */
  completedSteps: number[];
  /** 重置 */
  reset: () => void;
}

export function useWizard(options: UseWizardOptions): UseWizardReturn {
  const {
    steps,
    validateStep,
    onComplete,
    onStepChange,
    initialStep = 0,
  } = options;

  const [current, setCurrent] = useState(initialStep);
  const [isValidating, setIsValidating] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);

  const total = steps.length;

  const next = useCallback(async () => {
    if (current >= total - 1) {
      // 最后一步 → 完成
      onComplete?.();
      return;
    }

    // 验证当前步骤
    if (validateStep) {
      setIsValidating(true);
      try {
        const valid = await validateStep(current);
        if (!valid) {
          setIsValidating(false);
          return;
        }
      } catch {
        setIsValidating(false);
        return;
      }
      setIsValidating(false);
    }

    // 标记完成
    setCompletedSteps((prev) =>
      prev.includes(current) ? prev : [...prev, current],
    );

    const nextStep = current + 1;
    setCurrent(nextStep);
    onStepChange?.(nextStep);
  }, [current, total, validateStep, onComplete, onStepChange]);

  const prev = useCallback(() => {
    if (current <= 0) return;
    const prevStep = current - 1;
    setCurrent(prevStep);
    onStepChange?.(prevStep);
  }, [current, onStepChange]);

  const goTo = useCallback(
    (step: number) => {
      if (step < 0 || step >= total) return;
      setCurrent(step);
      onStepChange?.(step);
    },
    [total, onStepChange],
  );

  const reset = useCallback(() => {
    setCurrent(initialStep);
    setCompletedSteps([]);
    setIsValidating(false);
  }, [initialStep]);

  const progress = useMemo(
    () => (total > 1 ? Math.round((current / (total - 1)) * 100) : 100),
    [current, total],
  );

  return {
    current,
    currentName: steps[current] || "",
    total,
    isFirst: current === 0,
    isLast: current === total - 1,
    progress,
    next,
    prev,
    goTo,
    isValidating,
    completedSteps,
    reset,
  };
}

export default useWizard;
