/**
 * 在线状态 Hook（零依赖）。
 *
 * 功能：
 * - useOnlineStatus：检测网络连接状态
 * - 离线/在线事件回调
 * - 离线持续时间
 *
 * 用法：
 *   const { isOnline, offlineSince, offlineDuration } = useOnlineStatus();
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseOnlineStatusOptions {
  /** 上线回调 */
  onOnline?: () => void;
  /** 离线回调 */
  onOffline?: () => void;
}

interface UseOnlineStatusReturn {
  /** 是否在线 */
  isOnline: boolean;
  /** 离线起始时间（在线时为 null） */
  offlineSince: number | null;
  /** 离线持续时间（ms，在线时为 0） */
  offlineDuration: number;
  /** 连接类型（如果可用） */
  connectionType: string;
}

export function useOnlineStatus(options: UseOnlineStatusOptions = {}): UseOnlineStatusReturn {
  const { onOnline, onOffline } = options;

  const [isOnline, setIsOnline] = useState<boolean>(() =>
    typeof navigator !== "undefined" ? navigator.onLine : true,
  );
  const [offlineSince, setOfflineSince] = useState<number | null>(null);
  const [offlineDuration, setOfflineDuration] = useState(0);

  const callbacksRef = useRef({ onOnline, onOffline });
  callbacksRef.current = { onOnline, onOffline };
  const intervalRef = useRef<number>(0);

  const handleOnline = useCallback(() => {
    setIsOnline(true);
    setOfflineSince(null);
    setOfflineDuration(0);
    clearInterval(intervalRef.current);
    callbacksRef.current.onOnline?.();
  }, []);

  const handleOffline = useCallback(() => {
    const now = Date.now();
    setIsOnline(false);
    setOfflineSince(now);
    callbacksRef.current.onOffline?.();

    // 定期更新离线时长
    intervalRef.current = window.setInterval(() => {
      setOfflineDuration(Date.now() - now);
    }, 1000);
  }, []);

  useEffect(() => {
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      clearInterval(intervalRef.current);
    };
  }, [handleOnline, handleOffline]);

  // 连接类型
  const connectionType = (() => {
    const nav = navigator as any;
    return nav?.connection?.effectiveType || "unknown";
  })();

  return { isOnline, offlineSince, offlineDuration, connectionType };
}

export default useOnlineStatus;
