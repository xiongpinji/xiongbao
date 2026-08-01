/**
 * 按键检测 Hook（零依赖）。
 *
 * 功能：
 * - useKeyPress：检测特定键是否按下
 * - useKeys：多键组合状态
 * - 按键序列检测（如 Konami Code）
 *
 * 用法：
 *   const isEnterPressed = useKeyPress("Enter");
 *   const { ctrl, shift } = useKeys(["ctrl", "shift"]);
 *   const sequenceDone = useKeySequence(["ArrowUp", "ArrowUp", "ArrowDown"]);
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** 检测单个键是否按下 */
export function useKeyPress(targetKey: string): boolean {
  const [pressed, setPressed] = useState(false);

  useEffect(() => {
    const normalize = (key: string) => key.toLowerCase();
    const target = normalize(targetKey);

    const handleDown = (e: KeyboardEvent) => {
      if (normalize(e.key) === target || normalize(e.code) === target) {
        setPressed(true);
      }
    };

    const handleUp = (e: KeyboardEvent) => {
      if (normalize(e.key) === target || normalize(e.code) === target) {
        setPressed(false);
      }
    };

    // 窗口失焦时重置
    const handleBlur = () => setPressed(false);

    window.addEventListener("keydown", handleDown);
    window.addEventListener("keyup", handleUp);
    window.addEventListener("blur", handleBlur);

    return () => {
      window.removeEventListener("keydown", handleDown);
      window.removeEventListener("keyup", handleUp);
      window.removeEventListener("blur", handleBlur);
    };
  }, [targetKey]);

  return pressed;
}

/** 多键状态追踪 */
export function useKeys(
  keys: string[],
): Record<string, boolean> {
  const [state, setState] = useState<Record<string, boolean>>(
    () => Object.fromEntries(keys.map((k) => [k.toLowerCase(), false])),
  );

  useEffect(() => {
    const targets = new Set(keys.map((k) => k.toLowerCase()));

    const handleDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (targets.has(key) && !state[key]) {
        setState((prev) => ({ ...prev, [key]: true }));
      }
      // 修饰键
      if (e.ctrlKey && targets.has("ctrl")) setState((p) => ({ ...p, ctrl: true }));
      if (e.shiftKey && targets.has("shift")) setState((p) => ({ ...p, shift: true }));
      if (e.altKey && targets.has("alt")) setState((p) => ({ ...p, alt: true }));
      if (e.metaKey && targets.has("meta")) setState((p) => ({ ...p, meta: true }));
    };

    const handleUp = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (targets.has(key)) {
        setState((prev) => ({ ...prev, [key]: false }));
      }
      if (!e.ctrlKey && targets.has("ctrl")) setState((p) => ({ ...p, ctrl: false }));
      if (!e.shiftKey && targets.has("shift")) setState((p) => ({ ...p, shift: false }));
      if (!e.altKey && targets.has("alt")) setState((p) => ({ ...p, alt: false }));
      if (!e.metaKey && targets.has("meta")) setState((p) => ({ ...p, meta: false }));
    };

    const handleBlur = () => {
      setState(Object.fromEntries(keys.map((k) => [k.toLowerCase(), false])));
    };

    window.addEventListener("keydown", handleDown);
    window.addEventListener("keyup", handleUp);
    window.addEventListener("blur", handleBlur);

    return () => {
      window.removeEventListener("keydown", handleDown);
      window.removeEventListener("keyup", handleUp);
      window.removeEventListener("blur", handleBlur);
    };
  }, [keys]);

  return state;
}

/** 按键序列检测 */
export function useKeySequence(
  sequence: string[],
  options: { timeout?: number; onComplete?: () => void; loop?: boolean } = {},
): boolean {
  const { timeout = 2000, onComplete, loop = false } = options;
  const [completed, setCompleted] = useState(false);
  const indexRef = useRef(0);
  const timerRef = useRef<number>(0);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const expected = sequence[indexRef.current];
      if (e.key === expected || e.key.toLowerCase() === expected.toLowerCase()) {
        indexRef.current++;

        if (indexRef.current === sequence.length) {
          setCompleted(true);
          onComplete?.();
          indexRef.current = loop ? 0 : sequence.length;
        }

        // 重置超时
        clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(() => {
          indexRef.current = 0;
          if (!loop) setCompleted(false);
        }, timeout);
      } else {
        // 不匹配，重置
        indexRef.current = 0;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      clearTimeout(timerRef.current);
    };
  }, [sequence, timeout, onComplete, loop]);

  return completed;
}

export default useKeyPress;
