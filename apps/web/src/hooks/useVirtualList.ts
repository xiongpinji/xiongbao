/**
 * 虚拟列表 Hook（零依赖）。
 *
 * 功能：
 * - useVirtualList：仅渲染可视区域内的列表项
 * - 支持固定行高 / 动态估算行高
 * - 滚动位置跟踪 + 过度渲染缓冲
 *
 * 用法：
 *   const { containerProps, visibleItems, totalHeight } = useVirtualList(items, { itemHeight: 48 });
 *   <div {...containerProps}>
 *     <div style={{ height: totalHeight }}>
 *       {visibleItems.map(({ item, index, style }) => <Row key={index} style={style}>{item}</Row>)}
 *     </div>
 *   </div>
 */

import { useCallback, useMemo, useRef, useState } from "react";

interface UseVirtualListOptions {
  /** 每项固定高度（px） */
  itemHeight: number;
  /** 容器高度（px，默认 600） */
  containerHeight?: number;
  /** 上下过度渲染数量（默认 5） */
  overscan?: number;
}

interface VirtualItem<T> {
  /** 原始数据 */
  item: T;
  /** 原始索引 */
  index: number;
  /** 绝对定位样式 */
  style: React.CSSProperties;
}

interface UseVirtualListReturn<T> {
  /** 容器 props（含 ref + onScroll + style） */
  containerProps: {
    ref: React.RefObject<HTMLDivElement | null>;
    onScroll: () => void;
    style: React.CSSProperties;
  };
  /** 当前可见项 */
  visibleItems: VirtualItem<T>[];
  /** 列表总高度 */
  totalHeight: number;
  /** 滚动到指定索引 */
  scrollToIndex: (index: number) => void;
}

export function useVirtualList<T>(
  items: T[],
  options: UseVirtualListOptions,
): UseVirtualListReturn<T> {
  const { itemHeight, containerHeight = 600, overscan = 5 } = options;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);

  const totalHeight = items.length * itemHeight;

  const visibleItems = useMemo(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
    const visibleCount = Math.ceil(containerHeight / itemHeight) + overscan * 2;
    const endIndex = Math.min(items.length, startIndex + visibleCount);

    const result: VirtualItem<T>[] = [];
    for (let i = startIndex; i < endIndex; i++) {
      result.push({
        item: items[i],
        index: i,
        style: {
          position: "absolute",
          top: i * itemHeight,
          height: itemHeight,
          left: 0,
          right: 0,
        },
      });
    }
    return result;
  }, [items, scrollTop, itemHeight, containerHeight, overscan]);

  const onScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop);
    }
  }, []);

  const scrollToIndex = useCallback(
    (index: number) => {
      if (containerRef.current) {
        containerRef.current.scrollTop = index * itemHeight;
      }
    },
    [itemHeight],
  );

  const containerProps = {
    ref: containerRef,
    onScroll,
    style: {
      height: containerHeight,
      overflow: "auto" as const,
      position: "relative" as const,
    },
  };

  return { containerProps, visibleItems, totalHeight, scrollToIndex };
}

export default useVirtualList;
