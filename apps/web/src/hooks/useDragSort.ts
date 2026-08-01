/**
 * 轻量拖拽排序 Hook（零依赖，HTML5 Drag API）。
 *
 * 功能：
 * - useDragSort：管理列表拖拽重排
 * - 返回 dragProps / dropProps 供组件绑定
 * - 支持拖拽中视觉反馈（opacity）
 *
 * 用法：
 *   const { items, dragProps, dropProps, isDragging } = useDragSort(initialItems, onReorder);
 *   <li {...dragProps(i)} {...dropProps(i)}>{item.name}</li>
 */

import { useCallback, useRef, useState } from "react";

interface DragSortOptions<T> {
  items: T[];
  onReorder: (newItems: T[]) => void;
}

interface DragSortReturn {
  isDragging: boolean;
  dragIndex: number | null;
  /** 绑定到拖拽源元素 */
  getDragProps: (index: number) => {
    draggable: boolean;
    onDragStart: (e: React.DragEvent) => void;
    onDragEnd: () => void;
    style: React.CSSProperties;
  };
  /** 绑定到放置目标元素 */
  getDropProps: (index: number) => {
    onDragOver: (e: React.DragEvent) => void;
    onDrop: (e: React.DragEvent) => void;
  };
}

export function useDragSort<T>({ items, onReorder }: DragSortOptions<T>): DragSortReturn {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragIndexRef = useRef<number | null>(null);

  const getDragProps = useCallback(
    (index: number) => ({
      draggable: true,
      onDragStart: (e: React.DragEvent) => {
        dragIndexRef.current = index;
        setDragIndex(index);
        setIsDragging(true);
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(index));
      },
      onDragEnd: () => {
        setDragIndex(null);
        setIsDragging(false);
        dragIndexRef.current = null;
      },
      style: {
        opacity: dragIndex === index ? 0.5 : 1,
        cursor: "grab",
        transition: "opacity 0.15s",
      } as React.CSSProperties,
    }),
    [dragIndex],
  );

  const getDropProps = useCallback(
    (index: number) => ({
      onDragOver: (e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault();
        const from = dragIndexRef.current;
        if (from === null || from === index) return;

        const newItems = [...items];
        const [moved] = newItems.splice(from, 1);
        newItems.splice(index, 0, moved);
        onReorder(newItems);

        setDragIndex(null);
        setIsDragging(false);
        dragIndexRef.current = null;
      },
    }),
    [items, onReorder],
  );

  return { isDragging, dragIndex, getDragProps, getDropProps };
}

export default useDragSort;
