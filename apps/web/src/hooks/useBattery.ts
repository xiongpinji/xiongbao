/**
 * 电池状态 Hook（零依赖）。
 *
 * 功能：
 * - useBattery：Battery Status API 电量监听
 * - 充电状态 + 电量百分比
 * - 充电/放电时间估算
 *
 * 用法：
 *   const { level, charging, isSupported } = useBattery();
 *   <BatteryIcon level={level} charging={charging} />
 */

import { useEffect, useState } from "react";

interface BatteryState {
  /** 电量 0-1 */
  level: number | null;
  /** 是否充电中 */
  charging: boolean | null;
  /** 充满剩余时间（秒，Infinity=未知） */
  chargingTime: number | null;
  /** 放电剩余时间（秒，Infinity=未知） */
  dischargingTime: number | null;
}

interface UseBatteryReturn extends BatteryState {
  /** 是否支持 */
  isSupported: boolean;
  /** 电量百分比字符串 */
  levelPercent: string;
  /** 是否低电量（<20%） */
  isLow: boolean;
}

export function useBattery(): UseBatteryReturn {
  const [state, setState] = useState<BatteryState>({
    level: null,
    charging: null,
    chargingTime: null,
    dischargingTime: null,
  });

  const isSupported =
    typeof navigator !== "undefined" && "getBattery" in navigator;

  useEffect(() => {
    if (!isSupported) return;

    let battery: any = null;

    const update = () => {
      if (!battery) return;
      setState({
        level: battery.level,
        charging: battery.charging,
        chargingTime: battery.chargingTime,
        dischargingTime: battery.dischargingTime,
      });
    };

    (navigator as any).getBattery().then((b: any) => {
      battery = b;
      update();
      b.addEventListener("levelchange", update);
      b.addEventListener("chargingchange", update);
      b.addEventListener("chargingtimechange", update);
      b.addEventListener("dischargingtimechange", update);
    });

    return () => {
      if (battery) {
        battery.removeEventListener("levelchange", update);
        battery.removeEventListener("chargingchange", update);
        battery.removeEventListener("chargingtimechange", update);
        battery.removeEventListener("dischargingtimechange", update);
      }
    };
  }, [isSupported]);

  const levelPercent =
    state.level !== null ? `${Math.round(state.level * 100)}%` : "N/A";

  const isLow = state.level !== null && state.level < 0.2 && !state.charging;

  return { ...state, isSupported, levelPercent, isLow };
}

export default useBattery;
