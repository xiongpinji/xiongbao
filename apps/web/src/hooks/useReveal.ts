/**
 * 入场动画 Hook（零依赖）。
 *
 * 功能：
 * - useReveal：元素进入视口时触发入场动画
 * - 支持多种动画类型（fade/slide/scale）
 * - 可配置延迟/阈值/仅触发一次
 * - 返回 CSS 类名 + 内联样式
 *
 * 用法：
 *   const { ref, isVisible, className } = useReveal({ animation: "slideUp" });
 *   <div ref={ref} className={className}>内容</div>
 */

import { useEffect, useRef, useState } from "react";

type AnimationType = "fade" | "slideUp" | "slideDown" | "slideLeft" | "slideRight" | "scale" | "blur";

interface UseRevealOptions {
  /** 动画类型（默认 fade） */
  animation?: AnimationType;
  /** 动画时长（ms，默认 600） */
  duration?: number;
  /** 延迟（ms，默认 0） */
  delay?: number;
  /** IntersectionObserver 阈值（默认 0.1） */
  threshold?: number;
  /** 仅触发一次（默认 true） */
  once?: boolean;
  /** 初始偏移距离（px，默认 20） */
  distance?: number;
  /** 是否禁用 */
  disabled?: boolean;
}

interface UseRevealReturn {
  /** 绑定到元素 */
  ref: React.RefObject<HTMLElement | null>;
  /** 是否可见 */
  isVisible: boolean;
  /** 组合 className */
  className: string;
  /** 内联样式 */
  style: React.CSSProperties;
}

// 隐藏态变换
const HIDDEN_TRANSFORMS: Record<AnimationType, (d: number) => string> = {
  fade: () => "none",
  slideUp: (d) => `translateY(${d}px)`,
  slideDown: (d) => `translateY(-${d}px)`,
  slideLeft: (d) => `translateX(${d}px)`,
  slideRight: (d) => `translateX(-${d}px)`,
  scale: () => "scale(0.9)",
  blur: () => "none",
};

export function useReveal(options: UseRevealOptions = {}): UseRevealReturn {
  const {
    animation = "fade",
    duration = 600,
    delay = 0,
    threshold = 0.1,
    once = true,
    distance = 20,
    disabled = false,
  } = options;

  const ref = useRef<HTMLElement | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (disabled || typeof window === "undefined") {
      if (disabled) setIsVisible(true);
      return;
    }

    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          if (once) observer.unobserve(el);
        } else if (!once) {
          setIsVisible(false);
        }
      },
      { threshold },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [disabled, threshold, once]);

  const hiddenTransform = HIDDEN_TRANSFORMS[animation](distance);

  const style: React.CSSProperties = {
    opacity: isVisible ? 1 : 0,
    transform: isVisible ? "none" : hiddenTransform,
    filter: animation === "blur" && !isVisible ? "blur(8px)" : "none",
    transition: `opacity ${duration}ms ease ${delay}ms, transform ${duration}ms ease ${delay}ms, filter ${duration}ms ease ${delay}ms`,
    willChange: "opacity, transform",
  };

  const className = isVisible ? "reveal-visible" : "reveal-hidden";

  return { ref, isVisible, className, style };
}

export default useReveal;
