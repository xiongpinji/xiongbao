/**
 * 全屏控制 Hook（零依赖）。
 *
 * 功能：
 * - useFullscreen：元素全屏切换
 * - 全屏状态检测
 * - 全屏变化回调
 * - 兼容各浏览器前缀
 *
 * 用法：
 *   const { ref, isFullscreen, toggle, enter, exit } = useFullscreen();
 *   <div ref={ref}>
 *     <button onClick={toggle}>{isFullscreen ? "退出" : "全屏"}</button>
 *   </div>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseFullscreenOptions {
  /** 全屏变化回调 */
  onChange?: (isFullscreen: boolean) => void;
  /** 进入全屏回调 */
  onEnter?: () => void;
  /** 退出全屏回调 */
  onExit?: () => void;
}

interface UseFullscreenReturn {
  /** 绑定到目标元素 */
  ref: React.RefObject<HTMLElement | null>;
  /** 是否全屏 */
  isFullscreen: boolean;
  /** 是否支持全屏 */
  isSupported: boolean;
  /** 进入全屏 */
  enter: () => Promise<void>;
  /** 退出全屏 */
  exit: () => Promise<void>;
  /** 切换 */
  toggle: () => Promise<void>;
}

export function useFullscreen(
  options: UseFullscreenOptions = {},
): UseFullscreenReturn {
  const { onChange, onEnter, onExit } = options;

  const ref = useRef<HTMLElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const isSupported =
    typeof document !== "undefined" &&
    !!(
      document.documentElement.requestFullscreen ||
      (document.documentElement as any).webkitRequestFullscreen ||
      (document.documentElement as any).mozRequestFullScreen
    );

  useEffect(() => {
    const handler = () => {
      const active = !!document.fullscreenElement;
      setIsFullscreen(active);
      onChange?.(active);
      if (active) {
        onEnter?.();
      } else {
        onExit?.();
      }
    };

    document.addEventListener("fullscreenchange", handler);
    document.addEventListener("webkitfullscreenchange", handler);
    return () => {
      document.removeEventListener("fullscreenchange", handler);
      document.removeEventListener("webkitfullscreenchange", handler);
    };
  }, [onChange, onEnter, onExit]);

  const enter = useCallback(async () => {
    const element = ref.current || document.documentElement;
    try {
      if (element.requestFullscreen) {
        await element.requestFullscreen();
      } else if ((element as any).webkitRequestFullscreen) {
        (element as any).webkitRequestFullscreen();
      } else if ((element as any).mozRequestFullScreen) {
        (element as any).mozRequestFullScreen();
      }
    } catch {
      // 全屏请求被拒绝
    }
  }, []);

  const exit = useCallback(async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if ((document as any).webkitFullscreenElement) {
        (document as any).webkitExitFullscreen();
      }
    } catch {
      // 静默失败
    }
  }, []);

  const toggle = useCallback(async () => {
    if (isFullscreen) {
      await exit();
    } else {
      await enter();
    }
  }, [isFullscreen, enter, exit]);

  return { ref, isFullscreen, isSupported, enter, exit, toggle };
}

export default useFullscreen;
