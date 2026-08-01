/**
 * CSS 动画控制 Hook（零依赖）。
 *
 * 功能：
 * - useCSSAnimation：程序化控制 CSS 动画
 * - 播放/暂停/反转/重启
 * - 动画事件回调
 * - 动态关键帧注入
 *
 * 用法：
 *   const { ref, play, pause, isPlaying } = useCSSAnimation("fadeIn", {
 *     duration: 500,
 *     onComplete: () => console.log("done"),
 *   });
 *   <div ref={ref}>内容</div>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseCSSAnimationOptions {
  /** 动画时长（ms，默认 300） */
  duration?: number;
  /** 缓动函数（默认 ease） */
  easing?: string;
  /** 延迟（ms，默认 0） */
  delay?: number;
  /** 迭代次数（默认 1，Infinity=无限） */
  iterations?: number;
  /** 方向 */
  direction?: "normal" | "reverse" | "alternate" | "alternate-reverse";
  /** 填充模式 */
  fillMode?: "none" | "forwards" | "backwards" | "both";
  /** 自动播放（默认 false） */
  autoPlay?: boolean;
  /** 完成回调 */
  onComplete?: () => void;
  /** 开始回调 */
  onStart?: () => void;
}

interface UseCSSAnimationReturn {
  ref: React.RefObject<HTMLElement | null>;
  isPlaying: boolean;
  play: () => void;
  pause: () => void;
  stop: () => void;
  restart: () => void;
  reverse: () => void;
}

export function useCSSAnimation(
  animationName: string,
  options: UseCSSAnimationOptions = {},
): UseCSSAnimationReturn {
  const {
    duration = 300,
    easing = "ease",
    delay = 0,
    iterations = 1,
    direction = "normal",
    fillMode = "both",
    autoPlay = false,
    onComplete,
    onStart,
  } = options;

  const ref = useRef<HTMLElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const animationRef = useRef<Animation | null>(null);

  const play = useCallback(() => {
    const el = ref.current;
    if (!el) return;

    onStart?.();
    setIsPlaying(true);

    // 使用 Web Animations API
    const keyframes = getKeyframes(animationName);
    const anim = el.animate(keyframes, {
      duration,
      easing,
      delay,
      iterations,
      direction,
      fill: fillMode as FillMode,
    });

    animationRef.current = anim;

    anim.onfinish = () => {
      setIsPlaying(false);
      onComplete?.();
    };
  }, [animationName, duration, easing, delay, iterations, direction, fillMode, onComplete, onStart]);

  const pause = useCallback(() => {
    animationRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const stop = useCallback(() => {
    animationRef.current?.cancel();
    animationRef.current = null;
    setIsPlaying(false);
  }, []);

  const restart = useCallback(() => {
    stop();
    requestAnimationFrame(() => play());
  }, [stop, play]);

  const reverse = useCallback(() => {
    animationRef.current?.reverse();
  }, []);

  useEffect(() => {
    if (autoPlay) play();
    return () => {
      animationRef.current?.cancel();
    };
  }, []);

  return { ref, isPlaying, play, pause, stop, restart, reverse };
}

// 预设关键帧
function getKeyframes(name: string): Keyframe[] {
  const presets: Record<string, Keyframe[]> = {
    fadeIn: [{ opacity: 0 }, { opacity: 1 }],
    fadeOut: [{ opacity: 1 }, { opacity: 0 }],
    slideUp: [{ transform: "translateY(20px)", opacity: 0 }, { transform: "translateY(0)", opacity: 1 }],
    slideDown: [{ transform: "translateY(-20px)", opacity: 0 }, { transform: "translateY(0)", opacity: 1 }],
    scaleIn: [{ transform: "scale(0.9)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }],
    shake: [
      { transform: "translateX(0)" },
      { transform: "translateX(-5px)" },
      { transform: "translateX(5px)" },
      { transform: "translateX(-5px)" },
      { transform: "translateX(0)" },
    ],
    pulse: [{ transform: "scale(1)" }, { transform: "scale(1.05)" }, { transform: "scale(1)" }],
    spin: [{ transform: "rotate(0deg)" }, { transform: "rotate(360deg)" }],
  };

  return presets[name] || presets.fadeIn;
}

export default useCSSAnimation;
