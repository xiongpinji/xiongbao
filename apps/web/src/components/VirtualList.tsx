/**
 * 轻量虚拟列表组件（零依赖）。
 *
 * 仅渲染可视区域内的 DOM 节点，适合 1000+ 条数据：
 * - 固定行高模式（性能最优）
 * - 滚动缓冲（overscan）
 * - 支持自定义渲染
 *
 * 用法：
 *   <VirtualList
 *     items={logs}
 *     itemHeight={48}
 *     height={600}
 *     renderItem={(item, i) => <LogRow key={i} data={item} />}
 *   />
 */

import { useCallback, useRef, useState, type ReactNode } from "react";

interface VirtualListProps<T> {
  items: T[];
  itemHeight: number;
  height: number;
  renderItem: (item: T, index: number) => ReactNode;
  /** 上下额外渲染行数（默认 5） */
  overscan?: number;
  className?: string;
}

export function VirtualList<T>({
  items,
  itemHeight,
  height,
  renderItem,
  overscan = 5,
  className = "",
}: VirtualListProps<T>) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const totalHeight = items.length * itemHeight;
  const visibleCount = Math.ceil(height / itemHeight);

  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const endIndex = Math.min(items.length, startIndex + visibleCount + overscan * 2);

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop);
    }
  }, []);

  const visibleItems = items.slice(startIndex, endIndex);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className={`overflow-y-auto ${className}`}
      style={{ height }}
    >
      {/* 上方占位 */}
      <div style={{ height: startIndex * itemHeight }} />

      {/* 可视区域 */}
      {visibleItems.map((item, i) => (
        <div key={startIndex + i} style={{ height: itemHeight }}>
          {renderItem(item, startIndex + i)}
        </div>
      ))}

      {/* 下方占位 */}
      <div style={{ height: (items.length - endIndex) * itemHeight }} />
    </div>
  );
}

export default VirtualList;
