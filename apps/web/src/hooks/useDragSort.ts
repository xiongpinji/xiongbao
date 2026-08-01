/**
 * 拖拽排序 Hook（零依赖）。
 *
 * 功能：
 * - useDragSort：列表拖拽排序
 * - 拖拽状态追踪
 * - 排序回调
 *
 * 用法：
 *   const { items, dragIndex, overIndex, handlers } = useDragSort(initialItems, { onSort: setItems });
 *   {items.map((item, i) => <div key={item.id} {...handlers(i)}>{item.name}</div>)}
 */

import { useCallback, useRef, useState } from "react";

interface UseDragSortOptions<T> {
  /** 排序完成回调 */
  onSort?: (items: T[]) => void;
  /** 是否禁用 */
  disabled?: boolean;
  /** 方向 */
  direction?: "vertical" | "horizontal";
}

interface UseDragSortReturn<T> {
  /** 当前列表 */
  items: T[];
  /** 拖拽中的索引 */
  dragIndex: number | null;
  /** 悬停目标索引 */
  overIndex: number | null;
  /** 获取每项的事件 handlers */
  handlers: (index: number) => {
    draggable: boolean;
    onDragStart: (e: React.DragEvent) => void;
    onDragOver: (e: React.DragEvent) => void;
    onDragEnd: () => void;
    onDrop: (e: React.DragEvent) => void;
  };
  /** 手动设置列表 */
  setItems: (items: T[]) => void;
  /** 是否拖拽中 */
  isDragging: boolean;
}

export function useDragSort<T>(
  initialItems: T[],
  options: UseDragSortOptions<T> = {},
): UseDragSortReturn<T> {
  const { onSort, disabled = false, direction = "vertical" } = options;

  const [items, setItemsState] = useState<T[]>(initialItems);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  const onSortRef = useRef(onSort);
  onSortRef.current = onSort;

  const reorder = useCallback(
    (from: number, to: number) => {
      if (from === to) return;
      setItemsState((prev) => {
        const next = [...prev];
        const [moved] = next.splice(from, 1);
        next.splice(to, 0, moved);
        onSortRef.current?.(next);
        return next;
      });
    },
    [],
  );

  const handlers = useCallback(
    (index: number) => ({
      draggable: !disabled,
      onDragStart: (e: React.DragEvent) => {
        if (disabled) return;
        setDragIndex(index);
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(index));
      },
      onDragOver: (e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        if (dragIndex !== null && index !== overIndex) {
          setOverIndex(index);
        }
      },
      onDragEnd: () => {
        if (dragIndex !== null && overIndex !== null) {
          reorder(dragIndex, overIndex);
        }
        setDragIndex(null);
        setOverIndex(null);
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault();
        if (dragIndex !== null) {
          reorder(dragIndex, index);
        }
        setDragIndex(null);
        setOverIndex(null);
      },
    }),
    [disabled, dragIndex, overIndex, reorder],
  );

  const setItems = useCallback((newItems: T[]) => {
    setItemsState(newItems);
  }, []);

  return {
    items,
    dragIndex,
    overIndex,
    handlers,
    setItems,
    isDragging: dragIndex !== null,
  };
}

export default useDragSort;
