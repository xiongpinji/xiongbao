/**
 * 懒加载 Hook（零依赖）。
 *
 * 功能：
 * - useLazyLoad：进入视口时加载（图片/组件）
 * - useLazyImport：动态 import 封装
 * - 加载状态 + 错误处理
 *
 * 用法：
 *   // 图片懒加载
 *   const { ref, isVisible } = useLazyLoad();
 *   <img ref={ref} src={isVisible ? realSrc : placeholder} />
 *
 *   // 组件懒加载
 *   const { Component, isLoading, error } = useLazyImport(
 *     () => import("./HeavyChart"),
 *   );
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseLazyLoadOptions {
  /** 提前加载距离（px，默认 200） */
  rootMargin?: string;
  /** 可见比例（默认 0） */
  threshold?: number;
  /** 只触发一次（默认 true） */
  once?: boolean;
}

interface UseLazyLoadReturn {
  /** 绑定到目标元素 */
  ref: React.RefObject<HTMLElement>;
  /** 是否可见（已进入视口） */
  isVisible: boolean;
  /** 是否曾经可见过 */
  hasBeenVisible: boolean;
}

/**
 * 视口懒加载（IntersectionObserver）。
 */
export function useLazyLoad(options: UseLazyLoadOptions = {}): UseLazyLoadReturn {
  const { rootMargin = "200px", threshold = 0, once = true } = options;

  const ref = useRef<HTMLElement>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [hasBeenVisible, setHasBeenVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setIsVisible(true);
            setHasBeenVisible(true);
            if (once) observer.unobserve(entry.target);
          } else if (!once) {
            setIsVisible(false);
          }
        }
      },
      { rootMargin, threshold },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [rootMargin, threshold, once]);

  return { ref, isVisible, hasBeenVisible };
}

interface UseLazyImportReturn<T> {
  /** 加载的组件/模块 */
  module: T | null;
  /** 是否加载中 */
  isLoading: boolean;
  /** 错误 */
  error: Error | null;
  /** 手动触发加载 */
  load: () => void;
  /** 是否已加载 */
  isLoaded: boolean;
}

/**
 * 动态 import 懒加载。
 *
 * @param importFn 动态 import 函数
 * @param autoLoad 是否自动加载（默认 true）
 */
export function useLazyImport<T = any>(
  importFn: () => Promise<T>,
  autoLoad: boolean = true,
): UseLazyImportReturn<T> {
  const [module, setModule] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const loadedRef = useRef(false);

  const load = useCallback(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    setIsLoading(true);
    setError(null);

    importFn()
      .then((mod) => {
        setModule(mod);
        setIsLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e : new Error("Import failed"));
        setIsLoading(false);
        loadedRef.current = false; // 允许重试
      });
  }, [importFn]);

  useEffect(() => {
    if (autoLoad) load();
  }, [autoLoad, load]);

  return { module, isLoading, error, load, isLoaded: module !== null };
}

export default useLazyLoad;
