/**
 * 过渡动画 Hook（零依赖）。
 *
 * 功能：
 * - useTransition：元素进入/离开动画
 * - useMountTransition：挂载/卸载过渡
 * - 支持 CSS transition + 回调
 * - 列表项动画（stagger）
 *
 * 用法：
 *   const { isVisible, transitionProps } = useTransition(show, 300);
 *   {isVisible && <div {...transitionProps}>内容</div>}
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseTransitionOptions {
  /** 进入延迟（ms） */
  enterDelay?: number;
  /** 离开延迟（ms） */
  leaveDelay?: number;
  /** 进入回调 */
  onEnter?: () => void;
  /** 离开完成回调 */
  onExited?: () => void;
}

interface TransitionProps {
  style: React.CSSProperties;
  className: string;
}

interface UseTransitionReturn {
  /** 是否应渲染（包含离开动画期间） */
  isVisible: boolean;
  /** 是否处于进入状态 */
  isEntering: boolean;
  /** 是否处于离开状态 */
  isLeaving: boolean;
  /** 绑定到元素的 props */
  transitionProps: TransitionProps;
}

/**
 * 挂载/卸载过渡动画。
 *
 * @param mounted 是否显示
 * @param duration 动画时长（ms）
 */
export function useTransition(
  mounted: boolean,
  duration: number = 300,
  options: UseTransitionOptions = {},
): UseTransitionReturn {
  const { enterDelay = 0, leaveDelay = 0, onEnter, onExited } = options;

  const [isVisible, setIsVisible] = useState(mounted);
  const [phase, setPhase] = useState<"entering" | "entered" | "leaving" | "exited">(
    mounted ? "entered" : "exited",
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);

    if (mounted) {
      setIsVisible(true);
      setPhase("entering");
      onEnter?.();

      timerRef.current = setTimeout(() => {
        setPhase("entered");
      }, enterDelay + 16); // 一帧后切换到 entered
    } else {
      if (phase === "exited") return;
      setPhase("leaving");

      timerRef.current = setTimeout(() => {
        setPhase("exited");
        setIsVisible(false);
        onExited?.();
      }, duration + leaveDelay);
    }

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [mounted, duration, enterDelay, leaveDelay]);

  const transitionProps: TransitionProps = {
    style: {
      transition: `opacity ${duration}ms ease, transform ${duration}ms ease`,
      opacity: phase === "entering" || phase === "leaving" || phase === "exited" ? 0 : 1,
      transform:
        phase === "entering" || phase === "exited"
          ? "translateY(8px)"
          : phase === "leaving"
            ? "translateY(-8px)"
            : "translateY(0)",
    },
    className: phase === "entered" ? "transition-entered" : "transition-animating",
  };

  return {
    isVisible,
    isEntering: phase === "entering",
    isLeaving: phase === "leaving",
    transitionProps,
  };
}

/**
 * 列表项 stagger 动画。
 *
 * @param itemCount 列表项数量
 * @param staggerDelay 每项延迟（ms，默认 50）
 */
export function useStaggerTransition(
  itemCount: number,
  staggerDelay: number = 50,
  duration: number = 300,
) {
  const [visibleCount, setVisibleCount] = useState(0);

  useEffect(() => {
    let frame: number;
    let count = 0;

    const reveal = () => {
      count += 1;
      setVisibleCount(count);
      if (count < itemCount) {
        frame = requestAnimationFrame(() => {
          setTimeout(reveal, staggerDelay);
        });
      }
    };

    frame = requestAnimationFrame(reveal);
    return () => cancelAnimationFrame(frame);
  }, [itemCount, staggerDelay]);

  const getItemProps = useCallback(
    (index: number): TransitionProps => {
      const shown = index < visibleCount;
      return {
        style: {
          transition: `opacity ${duration}ms ease, transform ${duration}ms ease`,
          opacity: shown ? 1 : 0,
          transform: shown ? "translateY(0)" : "translateY(12px)",
        },
        className: shown ? "stagger-visible" : "stagger-hidden",
      };
    },
    [visibleCount, duration],
  );

  return { getItemProps, visibleCount, isComplete: visibleCount >= itemCount };
}

export default useTransition;
