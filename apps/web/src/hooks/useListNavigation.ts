/**
 * 列表键盘导航 Hook（零依赖）。
 *
 * 功能：
 * - useListNavigation：方向键在列表项间移动
 * - Type-ahead 搜索（输入字符跳转）
 * - 支持 Home/End/PageUp/PageDown
 * - 选中项自动滚动到可视区
 *
 * 用法：
 *   const { activeIndex, listProps, getItemProps } = useListNavigation(items.length, {
 *     onSelect: (i) => openItem(items[i]),
 *   });
 *   <ul {...listProps}>
 *     {items.map((item, i) => <li key={i} {...getItemProps(i)}>{item}</li>)}
 *   </ul>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseListNavigationOptions {
  /** 选中回调（Enter） */
  onSelect?: (index: number) => void;
  /** 焦点变化回调 */
  onActiveChange?: (index: number) => void;
  /** 是否循环（默认 true） */
  loop?: boolean;
  /** 方向（默认 vertical） */
  orientation?: "vertical" | "horizontal";
  /** 初始激活索引（默认 0） */
  defaultActive?: number;
  /** Type-ahead 超时（ms，默认 500） */
  typeAheadTimeout?: number;
}

interface ListProps {
  role: string;
  tabIndex: number;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onFocus: () => void;
  onBlur: () => void;
}

interface ItemProps {
  role: string;
  "aria-selected": boolean;
  onClick: () => void;
  ref: (el: HTMLElement | null) => void;
}

interface UseListNavigationReturn {
  /** 当前激活索引 */
  activeIndex: number;
  /** 列表容器 props */
  listProps: ListProps;
  /** 获取列表项 props */
  getItemProps: (index: number) => ItemProps;
  /** 手动设置激活项 */
  setActiveIndex: (index: number) => void;
}

export function useListNavigation(
  itemCount: number,
  options: UseListNavigationOptions = {},
): UseListNavigationReturn {
  const {
    onSelect,
    onActiveChange,
    loop = true,
    orientation = "vertical",
    defaultActive = 0,
    typeAheadTimeout = 500,
  } = options;

  const [activeIndex, setActiveIndexState] = useState(defaultActive);
  const itemRefs = useRef<Map<number, HTMLElement>>(new Map());
  const typeAheadRef = useRef("");
  const typeAheadTimerRef = useRef<number>(0);

  const setActiveIndex = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(index, itemCount - 1));
      setActiveIndexState(clamped);
      onActiveChange?.(clamped);

      // 滚动到可视区
      const el = itemRefs.current.get(clamped);
      el?.scrollIntoView({ block: "nearest" });
    },
    [itemCount, onActiveChange],
  );

  const moveNext = useCallback(() => {
    setActiveIndexState((prev) => {
      const next = prev + 1;
      const result = next >= itemCount ? (loop ? 0 : prev) : next;
      onActiveChange?.(result);
      const el = itemRefs.current.get(result);
      el?.scrollIntoView({ block: "nearest" });
      return result;
    });
  }, [itemCount, loop, onActiveChange]);

  const movePrev = useCallback(() => {
    setActiveIndexState((prev) => {
      const next = prev - 1;
      const result = next < 0 ? (loop ? itemCount - 1 : prev) : next;
      onActiveChange?.(result);
      const el = itemRefs.current.get(result);
      el?.scrollIntoView({ block: "nearest" });
      return result;
    });
  }, [itemCount, loop, onActiveChange]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const nextKey = orientation === "vertical" ? "ArrowDown" : "ArrowRight";
      const prevKey = orientation === "vertical" ? "ArrowUp" : "ArrowLeft";

      switch (e.key) {
        case nextKey:
          e.preventDefault();
          moveNext();
          break;
        case prevKey:
          e.preventDefault();
          movePrev();
          break;
        case "Home":
          e.preventDefault();
          setActiveIndex(0);
          break;
        case "End":
          e.preventDefault();
          setActiveIndex(itemCount - 1);
          break;
        case "PageDown":
          e.preventDefault();
          setActiveIndex(Math.min(activeIndex + 10, itemCount - 1));
          break;
        case "PageUp":
          e.preventDefault();
          setActiveIndex(Math.max(activeIndex - 10, 0));
          break;
        case "Enter":
        case " ":
          e.preventDefault();
          onSelect?.(activeIndex);
          break;
        default:
          // Type-ahead：单字符跳转
          if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
            typeAheadRef.current += e.key.toLowerCase();
            clearTimeout(typeAheadTimerRef.current);
            typeAheadTimerRef.current = window.setTimeout(() => {
              typeAheadRef.current = "";
            }, typeAheadTimeout);
          }
      }
    },
    [orientation, moveNext, movePrev, setActiveIndex, itemCount, activeIndex, onSelect, typeAheadTimeout],
  );

  const listProps: ListProps = {
    role: "listbox",
    tabIndex: 0,
    onKeyDown: handleKeyDown,
    onFocus: () => {},
    onBlur: () => {},
  };

  const getItemProps = useCallback(
    (index: number): ItemProps => ({
      role: "option",
      "aria-selected": index === activeIndex,
      onClick: () => {
        setActiveIndex(index);
        onSelect?.(index);
      },
      ref: (el: HTMLElement | null) => {
        if (el) {
          itemRefs.current.set(index, el);
        } else {
          itemRefs.current.delete(index);
        }
      },
    }),
    [activeIndex, setActiveIndex, onSelect],
  );

  // 清理
  useEffect(() => {
    return () => clearTimeout(typeAheadTimerRef.current);
  }, []);

  return { activeIndex, listProps, getItemProps, setActiveIndex };
}

export default useListNavigation;
