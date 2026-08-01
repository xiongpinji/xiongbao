/**
 * 图片懒加载 Hook（零依赖）。
 *
 * 功能：
 * - useImageLoader：图片进入视口时加载
 * - 加载状态（loading/loaded/error）
 * - 占位符 + 淡入效果
 * - 预加载支持
 *
 * 用法：
 *   const { ref, src, status } = useImageLoader("/api/media/img.png", {
 *     placeholder: "/placeholder.svg",
 *   });
 *   <img ref={ref} src={src} className={status === "loaded" ? "fade-in" : ""} />
 */

import { useCallback, useEffect, useRef, useState } from "react";

type ImageStatus = "idle" | "loading" | "loaded" | "error";

interface UseImageLoaderOptions {
  /** 占位图 URL */
  placeholder?: string;
  /** 是否立即加载（不懒加载，默认 false） */
  eager?: boolean;
  /** IntersectionObserver rootMargin（默认 200px） */
  rootMargin?: string;
  /** 加载成功回调 */
  onLoad?: () => void;
  /** 加载失败回调 */
  onError?: (error: string) => void;
}

interface UseImageLoaderReturn {
  /** 绑定到 img 元素的 ref */
  ref: React.RefObject<HTMLImageElement | null>;
  /** 当前应使用的 src */
  src: string;
  /** 加载状态 */
  status: ImageStatus;
  /** 是否可见 */
  isVisible: boolean;
  /** 手动重试 */
  retry: () => void;
}

export function useImageLoader(
  url: string,
  options: UseImageLoaderOptions = {},
): UseImageLoaderReturn {
  const {
    placeholder = "",
    eager = false,
    rootMargin = "200px",
    onLoad,
    onError,
  } = options;

  const ref = useRef<HTMLImageElement | null>(null);
  const [status, setStatus] = useState<ImageStatus>("idle");
  const [isVisible, setIsVisible] = useState(eager);
  const [shouldLoad, setShouldLoad] = useState(eager);

  // IntersectionObserver 懒加载
  useEffect(() => {
    if (eager) {
      setShouldLoad(true);
      return;
    }

    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setIsVisible(true);
          setShouldLoad(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [eager, rootMargin]);

  // 加载图片
  useEffect(() => {
    if (!shouldLoad || !url) return;

    setStatus("loading");

    const img = new Image();
    img.onload = () => {
      setStatus("loaded");
      onLoad?.();
    };
    img.onerror = () => {
      setStatus("error");
      onError?.("Image load failed");
    };
    img.src = url;

    // 如果已缓存
    if (img.complete) {
      setStatus("loaded");
      onLoad?.();
    }
  }, [shouldLoad, url, onLoad, onError]);

  const retry = useCallback(() => {
    setStatus("idle");
    setShouldLoad(false);
    // 下一帧重新触发
    requestAnimationFrame(() => setShouldLoad(true));
  }, []);

  const src = status === "loaded" ? url : placeholder || url;

  return { ref, src, status, isVisible, retry };
}

export default useImageLoader;
