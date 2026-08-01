/**
 * 手势识别 Hook（零依赖，移动端）。
 *
 * 功能：
 * - useSwipe：滑动方向检测
 * - useLongPress：长按检测
 * - 支持触摸 + 鼠标
 *
 * 用法：
 *   const swipeProps = useSwipe({
 *     onSwipeLeft: () => next(),
 *     onSwipeRight: () => prev(),
 *   });
 *   <div {...swipeProps}>滑动区域</div>
 */

import { useCallback, useRef } from "react";

interface UseSwipeOptions {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  onSwipeUp?: () => void;
  onSwipeDown?: () => void;
  /** 最小滑动距离（px，默认 50） */
  threshold?: number;
}

interface SwipeProps {
  onTouchStart: (e: React.TouchEvent) => void;
  onTouchEnd: (e: React.TouchEvent) => void;
  onMouseDown: (e: React.MouseEvent) => void;
  onMouseUp: (e: React.MouseEvent) => void;
}

export function useSwipe(options: UseSwipeOptions = {}): SwipeProps {
  const { onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown, threshold = 50 } = options;
  const startRef = useRef<{ x: number; y: number } | null>(null);

  const handleEnd = useCallback(
    (endX: number, endY: number) => {
      if (!startRef.current) return;
      const dx = endX - startRef.current.x;
      const dy = endY - startRef.current.y;
      startRef.current = null;

      const absDx = Math.abs(dx);
      const absDy = Math.abs(dy);

      if (Math.max(absDx, absDy) < threshold) return;

      if (absDx > absDy) {
        // 水平
        if (dx > 0) onSwipeRight?.();
        else onSwipeLeft?.();
      } else {
        // 垂直
        if (dy > 0) onSwipeDown?.();
        else onSwipeUp?.();
      }
    },
    [threshold, onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown],
  );

  return {
    onTouchStart: (e) => {
      const t = e.touches[0];
      startRef.current = { x: t.clientX, y: t.clientY };
    },
    onTouchEnd: (e) => {
      const t = e.changedTouches[0];
      handleEnd(t.clientX, t.clientY);
    },
    onMouseDown: (e) => {
      startRef.current = { x: e.clientX, y: e.clientY };
    },
    onMouseUp: (e) => {
      handleEnd(e.clientX, e.clientY);
    },
  };
}

interface UseLongPressOptions {
  /** 长按回调 */
  onLongPress: () => void;
  /** 长按时长（ms，默认 500） */
  duration?: number;
  /** 点击回调（非长按） */
  onClick?: () => void;
}

export function useLongPress(options: UseLongPressOptions) {
  const { onLongPress, duration = 500, onClick } = options;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isLongPress = useRef(false);

  const start = useCallback(() => {
    isLongPress.current = false;
    timerRef.current = setTimeout(() => {
      isLongPress.current = true;
      onLongPress();
    }, duration);
  }, [onLongPress, duration]);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (!isLongPress.current) {
      onClick?.();
    }
  }, [onClick]);

  return {
    onMouseDown: start,
    onMouseUp: stop,
    onMouseLeave: stop,
    onTouchStart: start,
    onTouchEnd: stop,
  };
}

export default useSwipe;
