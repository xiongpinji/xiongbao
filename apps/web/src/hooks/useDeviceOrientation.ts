/**
 * 设备方向 Hook（零依赖）。
 *
 * 功能：
 * - useDeviceOrientation：监听设备陀螺仪/加速度
 * - alpha/beta/gamma 角度
 * - 权限请求（iOS 13+）
 *
 * 用法：
 *   const { alpha, beta, gamma, requestPermission } = useDeviceOrientation();
 *   <div style={{ transform: `rotate(${gamma}deg)` }} />
 */

import { useCallback, useEffect, useState } from "react";

interface OrientationState {
  /** Z 轴旋转 (0-360) */
  alpha: number | null;
  /** X 轴倾斜 (-180~180) */
  beta: number | null;
  /** Y 轴倾斜 (-90~90) */
  gamma: number | null;
  /** 是否绝对方向 */
  absolute: boolean;
}

interface UseDeviceOrientationReturn extends OrientationState {
  /** 是否支持 */
  isSupported: boolean;
  /** 是否需要权限请求（iOS） */
  needsPermission: boolean;
  /** 请求权限 */
  requestPermission: () => Promise<boolean>;
  /** 是否已激活 */
  isActive: boolean;
}

export function useDeviceOrientation(): UseDeviceOrientationReturn {
  const [state, setState] = useState<OrientationState>({
    alpha: null,
    beta: null,
    gamma: null,
    absolute: false,
  });
  const [isActive, setIsActive] = useState(false);

  const isSupported =
    typeof window !== "undefined" && "DeviceOrientationEvent" in window;

  const needsPermission =
    typeof (DeviceOrientationEvent as any)?.requestPermission === "function";

  const handleOrientation = useCallback((event: DeviceOrientationEvent) => {
    setState({
      alpha: event.alpha,
      beta: event.beta,
      gamma: event.gamma,
      absolute: event.absolute,
    });
  }, []);

  const startListening = useCallback(() => {
    window.addEventListener("deviceorientation", handleOrientation);
    setIsActive(true);
  }, [handleOrientation]);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!isSupported) return false;

    if (needsPermission) {
      try {
        const result = await (DeviceOrientationEvent as any).requestPermission();
        if (result === "granted") {
          startListening();
          return true;
        }
        return false;
      } catch {
        return false;
      }
    }

    // 非 iOS 直接监听
    startListening();
    return true;
  }, [isSupported, needsPermission, startListening]);

  // 非 iOS 自动开始
  useEffect(() => {
    if (isSupported && !needsPermission) {
      startListening();
      return () => {
        window.removeEventListener("deviceorientation", handleOrientation);
        setIsActive(false);
      };
    }
  }, [isSupported, needsPermission, startListening, handleOrientation]);

  return {
    ...state,
    isSupported,
    needsPermission,
    requestPermission,
    isActive,
  };
}

export default useDeviceOrientation;
