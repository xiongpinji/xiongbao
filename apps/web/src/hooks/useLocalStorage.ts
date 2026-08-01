/**
 * 本地存储 Hook（零依赖）。
 *
 * 功能：
 * - useLocalStorage：响应式 localStorage 读写
 * - 自动 JSON 序列化/反序列化
 * - 跨标签页同步（storage 事件）
 * - SSR 安全
 *
 * 用法：
 *   const [value, setValue, remove] = useLocalStorage("key", defaultValue);
 *   setValue({ name: "test" }); // 自动 JSON.stringify
 */

import { useCallback, useEffect, useState } from "react";

type SetValue<T> = (value: T | ((prev: T) => T)) => void;

/**
 * 响应式 localStorage Hook。
 */
export function useLocalStorage<T>(
  key: string,
  initialValue: T,
): [T, SetValue<T>, () => void] {
  // 读取初始值
  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === "undefined") return initialValue;
    try {
      const item = window.localStorage.getItem(key);
      return item ? (JSON.parse(item) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  // 写入
  const setValue: SetValue<T> = useCallback(
    (value) => {
      setStoredValue((prev) => {
        const nextValue = value instanceof Function ? value(prev) : value;
        try {
          window.localStorage.setItem(key, JSON.stringify(nextValue));
        } catch {
          // 存储已满或不可用，静默失败
        }
        return nextValue;
      });
    },
    [key],
  );

  // 删除
  const remove = useCallback(() => {
    try {
      window.localStorage.removeItem(key);
      setStoredValue(initialValue);
    } catch {
      // 静默失败
    }
  }, [key, initialValue]);

  // 跨标签页同步
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key !== key) return;
      try {
        setStoredValue(e.newValue ? (JSON.parse(e.newValue) as T) : initialValue);
      } catch {
        // 解析失败忽略
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [key, initialValue]);

  return [storedValue, setValue, remove];
}

/**
 * sessionStorage 版本（会话级别）。
 */
export function useSessionStorage<T>(
  key: string,
  initialValue: T,
): [T, SetValue<T>, () => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === "undefined") return initialValue;
    try {
      const item = window.sessionStorage.getItem(key);
      return item ? (JSON.parse(item) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const setValue: SetValue<T> = useCallback(
    (value) => {
      setStoredValue((prev) => {
        const nextValue = value instanceof Function ? value(prev) : value;
        try {
          window.sessionStorage.setItem(key, JSON.stringify(nextValue));
        } catch {
          // 静默失败
        }
        return nextValue;
      });
    },
    [key],
  );

  const remove = useCallback(() => {
    try {
      window.sessionStorage.removeItem(key);
      setStoredValue(initialValue);
    } catch {
      // 静默失败
    }
  }, [key, initialValue]);

  return [storedValue, setValue, remove];
}

export default useLocalStorage;
