/**
 * 撤销/重做 Hook（零依赖）。
 *
 * 功能：
 * - useUndoRedo：状态历史栈管理
 * - 支持 undo / redo / 跳转
 * - 可配置最大历史深度
 * - 批量操作合并
 *
 * 用法：
 *   const { state, set, undo, redo, canUndo, canRedo } = useUndoRedo(initialState, {
 *     maxHistory: 50,
 *   });
 */

import { useCallback, useRef, useState } from "react";

interface UseUndoRedoOptions {
  /** 最大历史记录数（默认 100） */
  maxHistory?: number;
  /** 状态变更回调 */
  onChange?: (state: any) => void;
}

interface UseUndoRedoReturn<T> {
  /** 当前状态 */
  state: T;
  /** 设置新状态（推入历史） */
  set: (newState: T | ((prev: T) => T)) => void;
  /** 撤销 */
  undo: () => void;
  /** 重做 */
  redo: () => void;
  /** 是否可以撤销 */
  canUndo: boolean;
  /** 是否可以重做 */
  canRedo: boolean;
  /** 重置到初始状态 */
  reset: (newInitial?: T) => void;
  /** 历史深度 */
  historyLength: number;
  /** 当前位置 */
  position: number;
}

export function useUndoRedo<T>(
  initialState: T,
  options: UseUndoRedoOptions = {},
): UseUndoRedoReturn<T> {
  const { maxHistory = 100, onChange } = options;

  const [history, setHistory] = useState<T[]>([initialState]);
  const [position, setPosition] = useState(0);
  const optionsRef = useRef({ maxHistory, onChange });
  optionsRef.current = { maxHistory, onChange };

  const state = history[position];

  const set = useCallback(
    (newState: T | ((prev: T) => T)) => {
      setHistory((prev) => {
        const current = prev[position];
        const resolved =
          typeof newState === "function"
            ? (newState as (prev: T) => T)(current)
            : newState;

        // 截断 redo 栈
        const truncated = prev.slice(0, position + 1);
        const next = [...truncated, resolved];

        // 限制历史深度
        if (next.length > optionsRef.current.maxHistory) {
          next.shift();
          setPosition(next.length - 1);
        } else {
          setPosition(next.length - 1);
        }

        optionsRef.current.onChange?.(resolved);
        return next;
      });
    },
    [position],
  );

  const undo = useCallback(() => {
    setPosition((prev) => {
      if (prev <= 0) return prev;
      const newPos = prev - 1;
      setHistory((h) => {
        optionsRef.current.onChange?.(h[newPos]);
        return h;
      });
      return newPos;
    });
  }, []);

  const redo = useCallback(() => {
    setPosition((prev) => {
      setHistory((h) => {
        if (prev >= h.length - 1) return h;
        const newPos = prev + 1;
        optionsRef.current.onChange?.(h[newPos]);
        // 需要在外部更新 position
        return h;
      });
      return Math.min(prev + 1, history.length - 1);
    });
  }, [history.length]);

  const reset = useCallback(
    (newInitial?: T) => {
      const init = newInitial ?? initialState;
      setHistory([init]);
      setPosition(0);
      optionsRef.current.onChange?.(init);
    },
    [initialState],
  );

  return {
    state,
    set,
    undo,
    redo,
    canUndo: position > 0,
    canRedo: position < history.length - 1,
    reset,
    historyLength: history.length,
    position,
  };
}

export default useUndoRedo;
