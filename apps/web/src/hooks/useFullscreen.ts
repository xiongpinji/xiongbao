/**
 * 全屏 Hook（零依赖）。
 *
 * 功能：
 * - useFullscreen：元素全屏控制
 * - 全屏状态监听
 * - 进入/退出/切换
 *
 * 用法：
 *   const { ref, isFullscreen, enter, exit, toggle } = useFullscreen();
 *   <div ref={ref}><button onClick={toggle}>全屏</button></div>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseFullscreenOptions {
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
  /** 进入全屏 */
  enter: () => Promise<void>;
  /** 退出全屏 */
  exit: () => Promise<void>;
  /** 切换 */
  toggle: () => Promise<void>;
  /** 是否支持 */
  isSupported: boolean;
}

export function useFullscreen(options: UseFullscreenOptions = {}): UseFullscreenReturn {
  const { onEnter, onExit } = options;

  const ref = useRef<HTMLElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const callbacksRef = useRef({ onEnter, onExit });
  callbacksRef.current = { onEnter, onExit };

  const isSupported =
    typeof document !== "undefined" &&
    !!(document.documentElement.requestFullscreen || (document.documentElement as any).webkitRequestFullscreen);

  useEffect(() => {
    const handleChange = () => {
      const active = !!document.fullscreenElement;
      setIsFullscreen(active);
      if (active) {
        callbacksRef.current.onEnter?.();
      } else {
        callbacksRef.current.onExit?.();
      }
    };

    document.addEventListener("fullscreenchange", handleChange);
    document.addEventListener("webkitfullscreenchange", handleChange);

    return () => {
      document.removeEventListener("fullscreenchange", handleChange);
      document.removeEventListener("webkitfullscreenchange", handleChange);
    };
  }, []);

  const enter = useCallback(async () => {
    const el = ref.current || document.documentElement;
    try {
      if (el.requestFullscreen) {
        await el.requestFullscreen();
      } else if ((el as any).webkitRequestFullscreen) {
        (el as any).webkitRequestFullscreen();
      }
    } catch (e) {
      console.warn("useFullscreen: enter failed", e);
    }
  }, []);

  const exit = useCallback(async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if ((document as any).webkitFullscreenElement) {
        await (document as any).webkitExitFullscreen();
      }
    } catch (e) {
      console.warn("useFullscreen: exit failed", e);
    }
  }, []);

  const toggle = useCallback(async () => {
    if (isFullscreen) {
      await exit();
    } else {
      await enter();
    }
  }, [isFullscreen, enter, exit]);

  return { ref, isFullscreen, enter, exit, toggle, isSupported };
}

export default useFullscreen;
