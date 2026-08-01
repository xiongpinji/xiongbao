/**
 * 撤销重做 Hook（零依赖）。
 *
 * 功能：
 * - useUndoRedo：状态撤销/重做
 * - 历史记录栈
 * - 可配置最大历史
 *
 * 用法：
 *   const { state, set, undo, redo, canUndo, canRedo } = useUndoRedo(initialValue);
 */

import { useCallback, useRef, useState } from "react";

interface UseUndoRedoReturn<T> {
  /** 当前状态 */
  state: T;
  /** 设置新状态（推入历史） */
  set: (value: T | ((prev: T) => T)) => void;
  /** 撤销 */
  undo: () => void;
  /** 重做 */
  redo: () => void;
  /** 重置 */
  reset: (value?: T) => void;
  /** 是否可撤销 */
  canUndo: boolean;
  /** 是否可重做 */
  canRedo: boolean;
  /** 历史长度 */
  historyLength: number;
}

export function useUndoRedo<T>(
  initialValue: T,
  options: { maxHistory?: number } = {},
): UseUndoRedoReturn<T> {
  const { maxHistory = 50 } = options;

  const [state, setState] = useState<T>(initialValue);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);
  const [, forceRender] = useState(0);

  const rerender = useCallback(() => forceRender((n) => n + 1), []);

  const set = useCallback(
    (value: T | ((prev: T) => T)) => {
      setState((prev) => {
        const next = value instanceof Function ? value(prev) : value;
        if (next === prev) return prev;

        pastRef.current.push(prev);
        if (pastRef.current.length > maxHistory) {
          pastRef.current = pastRef.current.slice(-maxHistory);
        }
        futureRef.current = [];
        rerender();
        return next;
      });
    },
    [maxHistory, rerender],
  );

  const undo = useCallback(() => {
    if (pastRef.current.length === 0) return;

    setState((current) => {
      const previous = pastRef.current.pop()!;
      futureRef.current.push(current);
      rerender();
      return previous;
    });
  }, [rerender]);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;

    setState((current) => {
      const next = futureRef.current.pop()!;
      pastRef.current.push(current);
      rerender();
      return next;
    });
  }, [rerender]);

  const reset = useCallback(
    (value?: T) => {
      pastRef.current = [];
      futureRef.current = [];
      setState(value ?? initialValue);
      rerender();
    },
    [initialValue, rerender],
  );

  return {
    state,
    set,
    undo,
    redo,
    reset,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
    historyLength: pastRef.current.length,
  };
}

export default useUndoRedo;
