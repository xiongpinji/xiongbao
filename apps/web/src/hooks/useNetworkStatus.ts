/**
 * 网络状态 Hook（零依赖）。
 *
 * 功能：
 * - useNetworkStatus：在线/离线检测
 * - 连接类型（wifi/4g/ethernet）
 * - 网络变化回调
 *
 * 用法：
 *   const { isOnline, connectionType, effectiveType } = useNetworkStatus();
 *   if (!isOnline) showOfflineBanner();
 */

import { useCallback, useEffect, useState } from "react";

interface NetworkState {
  /** 是否在线 */
  isOnline: boolean;
  /** 连接类型（wifi/cellular/ethernet/none） */
  connectionType: string;
  /** 有效连接类型（slow-2g/2g/3g/4g） */
  effectiveType: string;
  /** 下行速度（Mbps） */
  downlink: number;
  /** RTT（ms） */
  rtt: number;
  /** 是否省流量模式 */
  saveData: boolean;
}

interface UseNetworkStatusOptions {
  /** 在线回调 */
  onOnline?: () => void;
  /** 离线回调 */
  onOffline?: () => void;
  /** 连接变化回调 */
  onChange?: (state: NetworkState) => void;
}

function getConnection(): any {
  if (typeof navigator === "undefined") return null;
  return (
    (navigator as any).connection ||
    (navigator as any).mozConnection ||
    (navigator as any).webkitConnection ||
    null
  );
}

function getNetworkState(): NetworkState {
  const conn = getConnection();
  return {
    isOnline: typeof navigator !== "undefined" ? navigator.onLine : true,
    connectionType: conn?.type || "unknown",
    effectiveType: conn?.effectiveType || "4g",
    downlink: conn?.downlink ?? 10,
    rtt: conn?.rtt ?? 50,
    saveData: conn?.saveData ?? false,
  };
}

export function useNetworkStatus(options: UseNetworkStatusOptions = {}): NetworkState {
  const { onOnline, onOffline, onChange } = options;
  const [state, setState] = useState<NetworkState>(getNetworkState);

  const updateState = useCallback(() => {
    const newState = getNetworkState();
    setState((prev) => {
      if (newState.isOnline && !prev.isOnline) onOnline?.();
      if (!newState.isOnline && prev.isOnline) onOffline?.();
      onChange?.(newState);
      return newState;
    });
  }, [onOnline, onOffline, onChange]);

  useEffect(() => {
    window.addEventListener("online", updateState);
    window.addEventListener("offline", updateState);

    const conn = getConnection();
    if (conn) {
      conn.addEventListener("change", updateState);
    }

    return () => {
      window.removeEventListener("online", updateState);
      window.removeEventListener("offline", updateState);
      if (conn) {
        conn.removeEventListener("change", updateState);
      }
    };
  }, [updateState]);

  return state;
}

export default useNetworkStatus;
