/**
 * 地理位置 Hook（零依赖）。
 *
 * 功能：
 * - useGeolocation：获取用户地理位置
 * - 持续监听 / 单次获取
 * - 错误处理 + 精度信息
 *
 * 用法：
 *   const { position, error, isLoading } = useGeolocation({ watch: true });
 *   <p>{position?.latitude}, {position?.longitude}</p>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface GeoPosition {
  latitude: number;
  longitude: number;
  accuracy: number;
  altitude: number | null;
  speed: number | null;
  heading: number | null;
  timestamp: number;
}

interface UseGeolocationOptions {
  /** 是否持续监听（默认 false） */
  watch?: boolean;
  /** 高精度（默认 false） */
  highAccuracy?: boolean;
  /** 超时 ms（默认 10000） */
  timeout?: number;
  /** 缓存时间 ms（默认 0） */
  maximumAge?: number;
}

interface UseGeolocationReturn {
  position: GeoPosition | null;
  error: string | null;
  isLoading: boolean;
  isSupported: boolean;
  /** 手动刷新位置 */
  refresh: () => void;
}

export function useGeolocation(
  options: UseGeolocationOptions = {},
): UseGeolocationReturn {
  const { watch = false, highAccuracy = false, timeout = 10000, maximumAge = 0 } = options;

  const [position, setPosition] = useState<GeoPosition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const watchIdRef = useRef<number | null>(null);

  const isSupported =
    typeof navigator !== "undefined" && !!navigator.geolocation;

  const getPosition = useCallback(() => {
    if (!isSupported) {
      setError("Geolocation not supported");
      return;
    }

    setIsLoading(true);
    setError(null);

    const opts: PositionOptions = {
      enableHighAccuracy: highAccuracy,
      timeout,
      maximumAge,
    };

    const onSuccess = (pos: GeolocationPosition) => {
      setPosition({
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        altitude: pos.coords.altitude,
        speed: pos.coords.speed,
        heading: pos.coords.heading,
        timestamp: pos.timestamp,
      });
      setIsLoading(false);
    };

    const onError = (err: GeolocationPositionError) => {
      const messages: Record<number, string> = {
        1: "位置权限被拒绝",
        2: "位置信息不可用",
        3: "获取位置超时",
      };
      setError(messages[err.code] || err.message);
      setIsLoading(false);
    };

    if (watch) {
      watchIdRef.current = navigator.geolocation.watchPosition(
        onSuccess,
        onError,
        opts,
      );
    } else {
      navigator.geolocation.getCurrentPosition(onSuccess, onError, opts);
    }
  }, [isSupported, watch, highAccuracy, timeout, maximumAge]);

  useEffect(() => {
    getPosition();
    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, [getPosition]);

  return { position, error, isLoading, isSupported, refresh: getPosition };
}

export default useGeolocation;
