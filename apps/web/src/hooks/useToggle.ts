/**
 * 切换状态 Hook（零依赖）。
 *
 * 功能：
 * - useToggle：布尔切换
 * - 支持多值循环
 * - 变化回调
 *
 * 用法：
 *   const [isOpen, toggle, setOpen] = useToggle(false);
 *   <button onClick={toggle}>{isOpen ? "关闭" : "打开"}</button>
 */

import { useCallback, useRef, useState } from "react";

/** 布尔切换。 */
export function useToggle(
  initialValue: boolean = false,
  onChange?: (value: boolean) => void,
): [boolean, () => void, (value: boolean) => void] {
  const [value, setValue] = useState(initialValue);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const toggle = useCallback(() => {
    setValue((prev) => {
      const next = !prev;
      onChangeRef.current?.(next);
      return next;
    });
  }, []);

  const set = useCallback((v: boolean) => {
    setValue((prev) => {
      if (prev === v) return prev;
      onChangeRef.current?.(v);
      return v;
    });
  }, []);

  return [value, toggle, set];
}

/** 多值循环切换。 */
export function useCycle<T>(
  values: T[],
  initialIndex: number = 0,
): [T, () => void, (index: number) => void, number] {
  const [index, setIndex] = useState(initialIndex % values.length);

  const cycle = useCallback(() => {
    setIndex((prev) => (prev + 1) % values.length);
  }, [values.length]);

  const goTo = useCallback(
    (i: number) => {
      setIndex(((i % values.length) + values.length) % values.length);
    },
    [values.length],
  );

  return [values[index], cycle, goTo, index];
}

export default useToggle;
