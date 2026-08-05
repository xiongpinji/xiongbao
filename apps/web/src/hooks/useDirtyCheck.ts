/**
 * 表单脏检查 Hook（零依赖）。
 *
 * 功能：
 * - useDirtyCheck：检测表单是否有未保存修改
 * - 字段级脏状态
 * - 离开页面警告（beforeunload）
 * - 重置到初始值
 *
 * 用法：
 *   const { isDirty, dirtyFields, track, reset } = useDirtyCheck(initialValues);
 *   <input onChange={(e) => track("name", e.target.value)} />
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface UseDirtyCheckOptions {
  /** 离开页面时警告（默认 true） */
  warnOnLeave?: boolean;
  /** 脏状态变化回调 */
  onDirtyChange?: (isDirty: boolean) => void;
}

interface UseDirtyCheckReturn<T extends Record<string, any>> {
  /** 是否有修改 */
  isDirty: boolean;
  /** 脏字段列表 */
  dirtyFields: string[];
  /** 追踪字段变化 */
  track: (field: keyof T & string, value: any) => void;
  /** 重置所有 */
  reset: (newInitial?: T) => void;
  /** 重置单字段 */
  resetField: (field: keyof T & string) => void;
  /** 当前值 */
  values: T;
  /** 字段是否脏 */
  isFieldDirty: (field: keyof T & string) => boolean;
}

export function useDirtyCheck<T extends Record<string, any>>(
  initialValues: T,
  options: UseDirtyCheckOptions = {},
): UseDirtyCheckReturn<T> {
  const { warnOnLeave = true, onDirtyChange } = options;

  const [values, setValues] = useState<T>(initialValues);
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(new Set());

  const initialRef = useRef<T>(initialValues);
  const prevDirtyRef = useRef(false);

  const isDirty = dirtyFields.size > 0;

  // 脏状态变化通知
  useEffect(() => {
    if (prevDirtyRef.current !== isDirty) {
      prevDirtyRef.current = isDirty;
      onDirtyChange?.(isDirty);
    }
  }, [isDirty, onDirtyChange]);

  // 离开页面警告
  useEffect(() => {
    if (!warnOnLeave) return;

    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyFields.size > 0) {
        e.preventDefault();
        e.returnValue = "";
      }
    };

    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [warnOnLeave, dirtyFields.size]);

  const track = useCallback(
    (field: keyof T & string, value: any) => {
      setValues((prev) => ({ ...prev, [field]: value }));

      // 比较初始值
      const isFieldDirty = JSON.stringify(value) !== JSON.stringify(initialRef.current[field]);
      setDirtyFields((prev) => {
        const next = new Set(prev);
        if (isFieldDirty) {
          next.add(field);
        } else {
          next.delete(field);
        }
        return next;
      });
    },
    [],
  );

  const reset = useCallback((newInitial?: T) => {
    const init = newInitial || initialRef.current;
    if (newInitial) initialRef.current = newInitial;
    setValues(init);
    setDirtyFields(new Set());
  }, []);

  const resetField = useCallback((field: keyof T & string) => {
    setValues((prev) => ({ ...prev, [field]: initialRef.current[field] }));
    setDirtyFields((prev) => {
      const next = new Set(prev);
      next.delete(field);
      return next;
    });
  }, []);

  const isFieldDirty = useCallback(
    (field: keyof T & string) => dirtyFields.has(field),
    [dirtyFields],
  );

  return {
    isDirty,
    dirtyFields: useMemo(() => Array.from(dirtyFields), [dirtyFields]),
    track,
    reset,
    resetField,
    values,
    isFieldDirty,
  };
}

export default useDirtyCheck;
