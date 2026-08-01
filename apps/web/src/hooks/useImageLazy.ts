/**
 * 图片懒加载 Hook（零依赖）。
 *
 * 功能：
 * - useImageLazy：进入视口时加载图片
 * - 加载状态（idle/loading/loaded/error）
 * - 占位/模糊效果
 * - 预加载距离
 *
 * 用法：
 *   const { ref, src, status } = useImageLazy("/img/photo.jpg");
 *   <img ref={ref} src={src} className={status === "loaded" ? "opacity-100" : "opacity-0"} />
 */

import { useCallback, useEffect, useRef, useState } from "react";

type ImageStatus = "idle" | "loading" | "loaded" | "error";

interface UseImageLazyOptions {
  /** 预加载距离（px，默认 200） */
  rootMargin?: string;
  /** 可见比例阈值 */
  threshold?: number;
  /** 加载完成回调 */
  onLoad?: () => void;
  /** 加载失败回调 */
  onError?: (error: Event) => void;
  /** 是否禁用（直接加载） */
  disabled?: boolean;
}

interface UseImageLazyReturn {
  /** 绑定到 img 或容器 */
  ref: React.RefCallback<HTMLElement>;
  /** 当前应设置的 src（未进入视口时为空） */
  src: string | undefined;
  /** 加载状态 */
  status: ImageStatus;
  /** 手动触发加载 */
  load: () => void;
}

export function useImageLazy(
  url: string,
  options: UseImageLazyOptions = {},
): UseImageLazyReturn {
  const {
    rootMargin = "200px",
    threshold = 0,
    onLoad,
    onError,
    disabled = false,
  } = options;

  const [status, setStatus] = useState<ImageStatus>(disabled ? "loading" : "idle");
  const [src, setSrc] = useState<string | undefined>(disabled ? url : undefined);

  const elRef = useRef<HTMLElement | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadedRef = useRef(false);
  const callbacksRef = useRef({ onLoad, onError });
  callbacksRef.current = { onLoad, onError };

  const startLoad = useCallback(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    setStatus("loading");
    setSrc(url);

    // 预加载图片
    const img = new Image();
    img.onload = () => {
      setStatus("loaded");
      callbacksRef.current.onLoad?.();
    };
    img.onerror = (e) => {
      setStatus("error");
      callbacksRef.current.onError?.(e);
    };
    img.src = url;
  }, [url]);

  const ref = useCallback(
    (el: HTMLElement | null) => {
      // 清理旧观察
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }

      elRef.current = el;

      if (!el || disabled || loadedRef.current) return;

      if (typeof IntersectionObserver === "undefined") {
        startLoad();
        return;
      }

      observerRef.current = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              startLoad();
              observerRef.current?.disconnect();
              break;
            }
          }
        },
        { rootMargin, threshold },
      );

      observerRef.current.observe(el);
    },
    [disabled, rootMargin, threshold, startLoad],
  );

  const load = useCallback(() => {
    startLoad();
  }, [startLoad]);

  useEffect(() => {
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  return { ref, src, status, load };
}

export default useImageLazy;
