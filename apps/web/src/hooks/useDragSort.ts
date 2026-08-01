/**
 * 拖拽排序 Hook（零依赖）。
 *
 * 功能：
 * - useDragSort：列表项拖拽重排
 * - 原生 HTML5 Drag & Drop API
 * - 拖拽状态跟踪 + 放置指示器
 *
 * 用法：
 *   const { items, dragProps, isDragging } = useDragSort(initialItems, {
 *     onReorder: (newItems) => saveOrder(newItems),
 *   });
 *   {items.map((item, i) => <div key={item.id} {...dragProps(i)}>{item.name}</div>)}
 */

import { useCallback, useRef, useState } from "react";

interface UseDragSortOptions<T> {
  /** 重排完成回调 */
  onReorder?: (items: T[]) => void;
  /** 是否禁用 */
  disabled?: boolean;
  /** 拖拽方向（默认 vertical） */
  axis?: "vertical" | "horizontal";
}

interface DragProps {
  draggable: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragEnd: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  "data-drag-index": number;
}

interface UseDragSortReturn<T> {
  /** 当前排序后的列表 */
  items: T[];
  /** 获取指定索引的拖拽 props */
  dragProps: (index: number) => DragProps;
  /** 是否正在拖拽 */
  isDragging: boolean;
  /** 当前拖拽索引 */
  dragIndex: number | null;
  /** 当前悬停目标索引 */
  overIndex: number | null;
  /** 手动设置列表（外部更新） */
  setItems: (items: T[]) => void;
}

export function useDragSort<T>(
  initialItems: T[],
  options: UseDragSortOptions<T> = {},
): UseDragSortReturn<T> {
  const { onReorder, disabled = false } = options;

  const [items, setItems] = useState<T[]>(initialItems);
  const [isDragging, setIsDragging] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const dragIndexRef = useRef<number | null>(null);

  const handleDragStart = useCallback(
    (index: number) => (e: React.DragEvent) => {
      if (disabled) return;
      dragIndexRef.current = index;
      setDragIndex(index);
      setIsDragging(true);
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(index));
    },
    [disabled],
  );

  const handleDragOver = useCallback(
    (index: number) => (e: React.DragEvent) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setOverIndex(index);
    },
    [],
  );

  const handleDrop = useCallback(
    (index: number) => (e: React.DragEvent) => {
      e.preventDefault();
      const from = dragIndexRef.current;
      if (from === null || from === index) {
        setIsDragging(false);
        setDragIndex(null);
        setOverIndex(null);
        return;
      }

      setItems((prev) => {
        const next = [...prev];
        const [moved] = next.splice(from, 1);
        next.splice(index, 0, moved);
        onReorder?.(next);
        return next;
      });

      setIsDragging(false);
      setDragIndex(null);
      setOverIndex(null);
      dragIndexRef.current = null;
    },
    [onReorder],
  );

  const handleDragEnd = useCallback(() => {
    setIsDragging(false);
    setDragIndex(null);
    setOverIndex(null);
    dragIndexRef.current = null;
  }, []);

  const dragProps = useCallback(
    (index: number): DragProps => ({
      draggable: !disabled,
      onDragStart: handleDragStart(index),
      onDragOver: handleDragOver(index),
      onDragEnd: handleDragEnd,
      onDrop: handleDrop(index),
      "data-drag-index": index,
    }),
    [disabled, handleDragStart, handleDragOver, handleDragEnd, handleDrop],
  );

  return { items, dragProps, isDragging, dragIndex, overIndex, setItems };
}

export default useDragSort;
