/**
 * 通用可见性检测 Hook（零依赖）。
 *
 * 功能：
 * - useInView：检测元素是否进入/离开视口
 * - 支持 once 模式（仅触发一次）
 * - 可配置 threshold / rootMargin
 * - 返回交叉比例
 *
 * 用法：
 *   const { ref, inView, ratio } = useInView({ threshold: 0.5, once: true });
 *   <div ref={ref}>{inView ? "可见" : "不可见"}</div>
 */

import { useEffect, useRef, useState } from "react";

interface UseInViewOptions {
  /** 可见比例阈值（默认 0） */
  threshold?: number | number[];
  /** 观察边距（默认 "0px"） */
  rootMargin?: string;
  /** 仅触发一次（默认 false） */
  once?: boolean;
  /** 根元素（默认 viewport） */
  root?: Element | null;
}

interface UseInViewReturn {
  /** 绑定到目标元素 */
  ref: React.RefObject<Element | null>;
  /** 是否可见 */
  inView: boolean;
  /** 交叉比例 (0-1) */
  ratio: number;
  /** 是否曾经可见 */
  hasBeenInView: boolean;
}

export function useInView(options: UseInViewOptions = {}): UseInViewReturn {
  const { threshold = 0, rootMargin = "0px", once = false, root = null } = options;

  const ref = useRef<Element | null>(null);
  const [inView, setInView] = useState(false);
  const [ratio, setRatio] = useState(0);
  const [hasBeenInView, setHasBeenInView] = useState(false);
  const onceRef = useRef(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (once && onceRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;

        const visible = entry.isIntersecting;
        setInView(visible);
        setRatio(entry.intersectionRatio);

        if (visible) {
          setHasBeenInView(true);
          if (once) {
            onceRef.current = true;
            observer.disconnect();
          }
        }
      },
      { threshold, rootMargin, root },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [threshold, rootMargin, root, once]);

  return { ref, inView, ratio, hasBeenInView };
}

export default useInView;
