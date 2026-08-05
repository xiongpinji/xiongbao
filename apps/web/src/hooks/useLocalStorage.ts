/**
 * 本地存储 Hook（零依赖）。
 *
 * 功能：
 * - useLocalStorage：状态与 localStorage 双向同步
 * - JSON 序列化/反序列化
 * - 跨标签页同步（storage 事件）
 * - 过期时间
 *
 * 用法：
 *   const [value, setValue, remove] = useLocalStorage("theme", "dark");
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface StorageMeta<T> {
  value: T;
  expires?: number; // 过期时间戳
}

type SetValue<T> = (value: T | ((prev: T) => T)) => void;

export function useLocalStorage<T>(
  key: string,
  initialValue: T,
  options: { ttlMs?: number; serialize?: (v: T) => string; deserialize?: (s: string) => T } = {},
): [T, SetValue<T>, () => void] {
  const { ttlMs, serialize = JSON.stringify, deserialize = JSON.parse } = options;

  const readValue = useCallback((): T => {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return initialValue;

      const meta: StorageMeta<T> = deserialize(raw);

      // 检查过期
      if (meta.expires && Date.now() > meta.expires) {
        localStorage.removeItem(key);
        return initialValue;
      }

      return meta.value !== undefined ? meta.value : (meta as unknown as T);
    } catch {
      return initialValue;
    }
  }, [key, initialValue, deserialize]);

  const [storedValue, setStoredValue] = useState<T>(readValue);
  const keyRef = useRef(key);
  keyRef.current = key;

  const setValue: SetValue<T> = useCallback(
    (value) => {
      setStoredValue((prev) => {
        const newValue = value instanceof Function ? value(prev) : value;
        try {
          const meta: StorageMeta<T> = {
            value: newValue,
            expires: ttlMs ? Date.now() + ttlMs : undefined,
          };
          localStorage.setItem(keyRef.current, serialize(meta));
        } catch (e) {
          console.warn(`useLocalStorage: failed to write key="${keyRef.current}"`, e);
        }
        return newValue;
      });
    },
    [serialize, ttlMs],
  );

  const remove = useCallback(() => {
    try {
      localStorage.removeItem(keyRef.current);
      setStoredValue(initialValue);
    } catch {
      // ignore
    }
  }, [initialValue]);

  // 跨标签页同步
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== keyRef.current) return;
      if (e.newValue === null) {
        setStoredValue(initialValue);
        return;
      }
      try {
        const meta: StorageMeta<T> = deserialize(e.newValue);
        if (meta.expires && Date.now() > meta.expires) {
          setStoredValue(initialValue);
        } else {
          setStoredValue(meta.value !== undefined ? meta.value : (meta as unknown as T));
        }
      } catch {
        setStoredValue(initialValue);
      }
    };

    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [initialValue, deserialize]);

  return [storedValue, setValue, remove];
}

export default useLocalStorage;
