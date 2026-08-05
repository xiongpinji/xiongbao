/**
 * 多选管理 Hook（零依赖）。
 *
 * 功能：
 * - useMultiSelect：列表多选状态管理
 * - 全选/反选/范围选择（Shift+Click）
 * - 选中计数 + 是否全选
 * - 键盘辅助（Ctrl+A）
 *
 * 用法：
 *   const { selected, toggle, selectAll, isSelected } = useMultiSelect(itemIds);
 *   {items.map(item => (
 *     <div key={item.id} onClick={() => toggle(item.id)} className={isSelected(item.id) ? "selected" : ""}>
 *       {item.name}
 *     </div>
 *   ))}
 */

import { useCallback, useMemo, useState } from "react";

interface UseMultiSelectOptions<T = string> {
  /** 初始选中项 */
  initialSelected?: T[];
  /** 选择变化回调 */
  onChange?: (selected: T[]) => void;
  /** 最大选择数（默认无限制） */
  maxSelected?: number;
}

interface UseMultiSelectReturn<T = string> {
  /** 选中集合 */
  selected: Set<T>;
  /** 选中数组 */
  selectedArray: T[];
  /** 选中数量 */
  count: number;
  /** 是否选中 */
  isSelected: (item: T) => boolean;
  /** 切换单项 */
  toggle: (item: T) => void;
  /** 选中 */
  select: (item: T) => void;
  /** 取消选中 */
  deselect: (item: T) => void;
  /** 全选 */
  selectAll: (items: T[]) => void;
  /** 清空 */
  clear: () => void;
  /** 反选 */
  invert: (items: T[]) => void;
  /** 范围选择（Shift+Click） */
  selectRange: (items: T[], from: T, to: T) => void;
  /** 是否全选 */
  isAllSelected: (items: T[]) => boolean;
  /** 是否部分选中 */
  isPartiallySelected: (items: T[]) => boolean;
}

export function useMultiSelect<T = string>(
  options: UseMultiSelectOptions<T> = {},
): UseMultiSelectReturn<T> {
  const { initialSelected, onChange, maxSelected } = options;

  const [selected, setSelected] = useState<Set<T>>(
    () => new Set(initialSelected || []),
  );

  const emitChange = useCallback(
    (next: Set<T>) => {
      setSelected(next);
      onChange?.(Array.from(next));
    },
    [onChange],
  );

  const isSelected = useCallback((item: T) => selected.has(item), [selected]);

  const toggle = useCallback(
    (item: T) => {
      const next = new Set(selected);
      if (next.has(item)) {
        next.delete(item);
      } else {
        if (maxSelected && next.size >= maxSelected) return;
        next.add(item);
      }
      emitChange(next);
    },
    [selected, maxSelected, emitChange],
  );

  const select = useCallback(
    (item: T) => {
      if (selected.has(item)) return;
      if (maxSelected && selected.size >= maxSelected) return;
      const next = new Set(selected);
      next.add(item);
      emitChange(next);
    },
    [selected, maxSelected, emitChange],
  );

  const deselect = useCallback(
    (item: T) => {
      if (!selected.has(item)) return;
      const next = new Set(selected);
      next.delete(item);
      emitChange(next);
    },
    [selected, emitChange],
  );

  const selectAll = useCallback(
    (items: T[]) => {
      const next = new Set(selected);
      for (const item of items) {
        if (maxSelected && next.size >= maxSelected) break;
        next.add(item);
      }
      emitChange(next);
    },
    [selected, maxSelected, emitChange],
  );

  const clear = useCallback(() => {
    emitChange(new Set());
  }, [emitChange]);

  const invert = useCallback(
    (items: T[]) => {
      const next = new Set<T>();
      for (const item of items) {
        if (!selected.has(item)) {
          if (maxSelected && next.size >= maxSelected) break;
          next.add(item);
        }
      }
      emitChange(next);
    },
    [selected, maxSelected, emitChange],
  );

  const selectRange = useCallback(
    (items: T[], from: T, to: T) => {
      const fromIdx = items.indexOf(from);
      const toIdx = items.indexOf(to);
      if (fromIdx === -1 || toIdx === -1) return;

      const [start, end] = fromIdx < toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx];
      const next = new Set(selected);
      for (let i = start; i <= end; i++) {
        if (maxSelected && next.size >= maxSelected) break;
        next.add(items[i]);
      }
      emitChange(next);
    },
    [selected, maxSelected, emitChange],
  );

  const isAllSelected = useCallback(
    (items: T[]) => items.length > 0 && items.every((i) => selected.has(i)),
    [selected],
  );

  const isPartiallySelected = useCallback(
    (items: T[]) => {
      const count = items.filter((i) => selected.has(i)).length;
      return count > 0 && count < items.length;
    },
    [selected],
  );

  const selectedArray = useMemo(() => Array.from(selected), [selected]);

  return {
    selected,
    selectedArray,
    count: selected.size,
    isSelected,
    toggle,
    select,
    deselect,
    selectAll,
    clear,
    invert,
    selectRange,
    isAllSelected,
    isPartiallySelected,
  };
}

export default useMultiSelect;
