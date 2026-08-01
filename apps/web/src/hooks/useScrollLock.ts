/**
 * 滚动锁定 Hook（零依赖）。
 *
 * 功能：
 * - useScrollLock：锁定页面滚动（模态框/抽屉打开时）
 * - 自动保存/恢复滚动位置
 * - 防止滚动穿透
 * - 多实例引用计数
 *
 * 用法：
 *   const lockScroll = useScrollLock();
 *   useEffect(() => {
 *     if (isModalOpen) lockScroll();
 *     return () => unlockScroll();
 *   }, [isModalOpen]);
 */

import { useCallback, useEffect, useRef } from "react";

// 全局引用计数
let lockCount = 0;
let savedScrollY = 0;
let savedOverflow = "";
let savedPaddingRight = "";

function getScrollbarWidth(): number {
  if (typeof window === "undefined") return 0;
  return window.innerWidth - document.documentElement.clientWidth;
}

function lock(): void {
  lockCount++;
  if (lockCount > 1) return; // 已锁定

  savedScrollY = window.scrollY;
  savedOverflow = document.body.style.overflow;
  savedPaddingRight = document.body.style.paddingRight;

  const scrollbarWidth = getScrollbarWidth();

  document.body.style.overflow = "hidden";
  if (scrollbarWidth > 0) {
    document.body.style.paddingRight = `${scrollbarWidth}px`;
  }

  // 固定定位防止 iOS 弹性滚动
  document.body.style.position = "fixed";
  document.body.style.top = `-${savedScrollY}px`;
  document.body.style.width = "100%";
}

function unlock(): void {
  if (lockCount <= 0) return;
  lockCount--;
  if (lockCount > 0) return; // 还有其他锁定

  document.body.style.overflow = savedOverflow;
  document.body.style.paddingRight = savedPaddingRight;
  document.body.style.position = "";
  document.body.style.top = "";
  document.body.style.width = "";

  // 恢复滚动位置
  window.scrollTo(0, savedScrollY);
}

export function useScrollLock(): {
  lock: () => void;
  unlock: () => void;
  isLocked: () => boolean;
} {
  const isLockedRef = useRef(false);

  const doLock = useCallback(() => {
    if (!isLockedRef.current) {
      lock();
      isLockedRef.current = true;
    }
  }, []);

  const doUnlock = useCallback(() => {
    if (isLockedRef.current) {
      unlock();
      isLockedRef.current = false;
    }
  }, []);

  const isLocked = useCallback(() => isLockedRef.current, []);

  // 组件卸载时自动解锁
  useEffect(() => {
    return () => {
      if (isLockedRef.current) {
        unlock();
        isLockedRef.current = false;
      }
    };
  }, []);

  return { lock: doLock, unlock: doUnlock, isLocked };
}

/** 条件锁定（传入 true 自动锁定） */
export function useConditionalScrollLock(active: boolean): void {
  const { lock, unlock } = useScrollLock();

  useEffect(() => {
    if (active) {
      lock();
      return () => unlock();
    }
  }, [active, lock, unlock]);
}

export default useScrollLock;
