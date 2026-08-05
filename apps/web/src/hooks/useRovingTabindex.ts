/**
 * Roving Tabindex Hook（零依赖）。
 *
 * 功能：
 * - useRovingTabindex：键盘无障碍列表导航
 * - WAI-ARIA 推荐模式
 * - 方向键移动焦点
 * - Home/End 跳转
 *
 * 用法：
 *   const { containerProps, getItemProps } = useRovingTabindex(itemCount, {
 *     orientation: "vertical",
 *   });
 *   <ul {...containerProps}>
 *     {items.map((_, i) => <li key={i} {...getItemProps(i)}>...</li>)}
 *   </ul>
 */

import { useCallback, useRef, useState } from "react";

interface UseRovingTabindexOptions {
  /** 方向（默认 vertical） */
  orientation?: "vertical" | "horizontal" | "both";
  /** 是否循环（默认 true） */
  loop?: boolean;
  /** 焦点变化回调 */
  onActiveChange?: (index: number) => void;
}

interface ContainerProps {
  role: string;
  onKeyDown: (e: React.KeyboardEvent) => void;
}

interface ItemProps {
  tabIndex: number;
  ref: (el: HTMLElement | null) => void;
  onFocus: () => void;
}

interface UseRovingTabindexReturn {
  /** 容器 props */
  containerProps: ContainerProps;
  /** 获取项 props */
  getItemProps: (index: number) => ItemProps;
  /** 当前活跃索引 */
  activeIndex: number;
  /** 设置活跃索引 */
  setActiveIndex: (index: number) => void;
}

export function useRovingTabindex(
  itemCount: number,
  options: UseRovingTabindexOptions = {},
): UseRovingTabindexReturn {
  const { orientation = "vertical", loop = true, onActiveChange } = options;

  const [activeIndex, setActiveIndexState] = useState(0);
  const itemRefs = useRef<(HTMLElement | null)[]>([]);

  const setActiveIndex = useCallback(
    (index: number) => {
      setActiveIndexState(index);
      onActiveChange?.(index);
      itemRefs.current[index]?.focus();
    },
    [onActiveChange],
  );

  const moveNext = useCallback(() => {
    setActiveIndexState((prev) => {
      const next = prev + 1 >= itemCount ? (loop ? 0 : prev) : prev + 1;
      onActiveChange?.(next);
      itemRefs.current[next]?.focus();
      return next;
    });
  }, [itemCount, loop, onActiveChange]);

  const movePrev = useCallback(() => {
    setActiveIndexState((prev) => {
      const next = prev - 1 < 0 ? (loop ? itemCount - 1 : prev) : prev - 1;
      onActiveChange?.(next);
      itemRefs.current[next]?.focus();
      return next;
    });
  }, [itemCount, loop, onActiveChange]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const nextKeys =
        orientation === "horizontal"
          ? ["ArrowRight"]
          : orientation === "vertical"
            ? ["ArrowDown"]
            : ["ArrowDown", "ArrowRight"];

      const prevKeys =
        orientation === "horizontal"
          ? ["ArrowLeft"]
          : orientation === "vertical"
            ? ["ArrowUp"]
            : ["ArrowUp", "ArrowLeft"];

      if (nextKeys.includes(e.key)) {
        e.preventDefault();
        moveNext();
      } else if (prevKeys.includes(e.key)) {
        e.preventDefault();
        movePrev();
      } else if (e.key === "Home") {
        e.preventDefault();
        setActiveIndex(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setActiveIndex(itemCount - 1);
      }
    },
    [orientation, moveNext, movePrev, setActiveIndex, itemCount],
  );

  const containerProps: ContainerProps = {
    role: "listbox",
    onKeyDown: handleKeyDown,
  };

  const getItemProps = useCallback(
    (index: number): ItemProps => ({
      tabIndex: index === activeIndex ? 0 : -1,
      ref: (el: HTMLElement | null) => {
        itemRefs.current[index] = el;
      },
      onFocus: () => {
        setActiveIndexState(index);
      },
    }),
    [activeIndex],
  );

  return { containerProps, getItemProps, activeIndex, setActiveIndex };
}

export default useRovingTabindex;
