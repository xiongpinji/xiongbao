/**
 * 键盘导航 Hook（零依赖）。
 *
 * 功能：
 * - useKeyboardNav：列表/菜单方向键导航
 * - 支持上下左右 + Home/End + Enter 选中
 * - 循环模式（可选）
 * - 输入框内自动忽略
 *
 * 用法：
 *   const { activeIndex, setActiveIndex, onKeyDown } = useKeyboardNav({
 *     itemCount: items.length,
 *     onSelect: (i) => handleSelect(items[i]),
 *   });
 *   <ul onKeyDown={onKeyDown}>
 *     {items.map((item, i) => (
 *       <li className={i === activeIndex ? "active" : ""}>{item}</li>
 *     ))}
 *   </ul>
 */

import { useCallback, useRef, useState } from "react";

interface UseKeyboardNavOptions {
  /** 列表项数量 */
  itemCount: number;
  /** 选中回调（Enter） */
  onSelect?: (index: number) => void;
  /** 是否循环（默认 true） */
  loop?: boolean;
  /** 方向（默认 vertical） */
  orientation?: "vertical" | "horizontal" | "both";
  /** 初始激活索引 */
  initialIndex?: number;
}

interface UseKeyboardNavReturn {
  /** 当前激活索引（-1 表示无） */
  activeIndex: number;
  /** 手动设置激活索引 */
  setActiveIndex: (index: number) => void;
  /** 绑定到容器的 onKeyDown */
  onKeyDown: (e: React.KeyboardEvent) => void;
  /** 重置 */
  reset: () => void;
}

export function useKeyboardNav(options: UseKeyboardNavOptions): UseKeyboardNavReturn {
  const {
    itemCount,
    onSelect,
    loop = true,
    orientation = "vertical",
    initialIndex = -1,
  } = options;

  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const itemCountRef = useRef(itemCount);
  itemCountRef.current = itemCount;

  const move = useCallback(
    (direction: "next" | "prev" | "first" | "last") => {
      setActiveIndex((prev) => {
        const count = itemCountRef.current;
        if (count === 0) return -1;

        switch (direction) {
          case "first":
            return 0;
          case "last":
            return count - 1;
          case "next": {
            if (prev < count - 1) return prev + 1;
            return loop ? 0 : prev;
          }
          case "prev": {
            if (prev > 0) return prev - 1;
            return loop ? count - 1 : prev;
          }
        }
      });
    },
    [loop],
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // 输入框内忽略
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      const nextKeys =
        orientation === "horizontal"
          ? ["ArrowRight"]
          : orientation === "both"
            ? ["ArrowDown", "ArrowRight"]
            : ["ArrowDown"];

      const prevKeys =
        orientation === "horizontal"
          ? ["ArrowLeft"]
          : orientation === "both"
            ? ["ArrowUp", "ArrowLeft"]
            : ["ArrowUp"];

      if (nextKeys.includes(e.key)) {
        e.preventDefault();
        move("next");
      } else if (prevKeys.includes(e.key)) {
        e.preventDefault();
        move("prev");
      } else if (e.key === "Home") {
        e.preventDefault();
        move("first");
      } else if (e.key === "End") {
        e.preventDefault();
        move("last");
      } else if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        onSelect?.(activeIndex);
      }
    },
    [move, onSelect, activeIndex, orientation],
  );

  const reset = useCallback(() => {
    setActiveIndex(initialIndex);
  }, [initialIndex]);

  return { activeIndex, setActiveIndex, onKeyDown, reset };
}

export default useKeyboardNav;
