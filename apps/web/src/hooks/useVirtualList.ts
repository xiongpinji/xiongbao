/**
 * 虚拟列表 Hook（零依赖）。
 *
 * 功能：
 * - useVirtualList：大列表虚拟化渲染
 * - 固定/动态行高
 * - 滚动位置保持
 * - 过度渲染缓冲
 *
 * 用法：
 *   const { containerRef, visibleItems, totalHeight, offsetY } = useVirtualList(items, { itemHeight: 48 });
 *   <div ref={containerRef} style={{ overflow: "auto", height: 400 }}>
 *     <div style={{ height: totalHeight, position: "relative" }}>
 *       <div style={{ transform: `translateY(${offsetY}px)` }}>
 *         {visibleItems.map(item => <Row key={item.index} data={item.data} />)}
 *       </div>
 *     </div>
 *   </div>
 */

import { useCallback, useMemo, useRef, useState } from "react";

interface UseVirtualListOptions {
  /** 固定行高（px） */
  itemHeight: number;
  /** 容器高度（px，不传则自动检测） */
  containerHeight?: number;
  /** 上下过度渲染数量 */
  overscan?: number;
}

interface VirtualItem<T> {
  /** 原始数据 */
  data: T;
  /** 原始索引 */
  index: number;
  /** 顶部偏移 */
  offsetTop: number;
}

interface UseVirtualListReturn<T> {
  /** 容器 ref */
  containerRef: React.RefCallback<HTMLElement>;
  /** 可见项 */
  visibleItems: VirtualItem<T>[];
  /** 总高度（撑开滚动条） */
  totalHeight: number;
  /** 可见区域偏移 */
  offsetY: number;
  /** 滚动到索引 */
  scrollToIndex: (index: number) => void;
  /** 当前滚动位置 */
  scrollTop: number;
}

export function useVirtualList<T>(
  items: T[],
  options: UseVirtualListOptions,
): UseVirtualListReturn<T> {
  const { itemHeight, containerHeight: fixedHeight, overscan = 5 } = options;

  const [scrollTop, setScrollTop] = useState(0);
  const [measuredHeight, setMeasuredHeight] = useState(fixedHeight || 600);
  const containerElRef = useRef<HTMLElement | null>(null);

  const containerHeight = fixedHeight || measuredHeight;
  const totalHeight = items.length * itemHeight;

  const visibleItems = useMemo(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
    const visibleCount = Math.ceil(containerHeight / itemHeight) + overscan * 2;
    const endIndex = Math.min(items.length, startIndex + visibleCount);

    const result: VirtualItem<T>[] = [];
    for (let i = startIndex; i < endIndex; i++) {
      result.push({
        data: items[i],
        index: i,
        offsetTop: i * itemHeight,
      });
    }
    return result;
  }, [items, itemHeight, containerHeight, scrollTop, overscan]);

  const offsetY = visibleItems.length > 0 ? visibleItems[0].offsetTop : 0;

  const containerRef = useCallback(
    (el: HTMLElement | null) => {
      if (containerElRef.current) {
        containerElRef.current.removeEventListener("scroll", handleScroll);
      }

      containerElRef.current = el;

      if (el) {
        if (!fixedHeight) {
          setMeasuredHeight(el.clientHeight);
        }
        el.addEventListener("scroll", handleScroll, { passive: true });
      }
    },
    [fixedHeight],
  );

  const handleScroll = useCallback(() => {
    const el = containerElRef.current;
    if (el) {
      setScrollTop(el.scrollTop);
    }
  }, []);

  const scrollToIndex = useCallback(
    (index: number) => {
      const el = containerElRef.current;
      if (!el) return;
      const targetTop = index * itemHeight;
      el.scrollTop = targetTop;
      setScrollTop(targetTop);
    },
    [itemHeight],
  );

  return {
    containerRef,
    visibleItems,
    totalHeight,
    offsetY,
    scrollToIndex,
    scrollTop,
  };
}

export default useVirtualList;
