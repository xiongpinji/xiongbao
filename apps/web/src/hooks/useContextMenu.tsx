/**
 * 右键菜单 Hook（零依赖）。
 *
 * 功能：
 * - useContextMenu：自定义右键菜单
 * - 支持菜单项分组 / 分隔线 / 禁用
 * - 自动定位（边界检测）
 * - 点击外部 / Esc 关闭
 *
 * 用法：
 *   const { open, menuProps, MenuItem } = useContextMenu([
 *     { label: "编辑", onClick: () => edit(item) },
 *     { type: "divider" },
 *     { label: "删除", danger: true, onClick: () => remove(item) },
 *   ]);
 *   <div onContextMenu={open}>右键我</div>
 *   <MenuPortal />
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface MenuItemConfig {
  type?: "item" | "divider";
  label?: string;
  icon?: string;
  danger?: boolean;
  disabled?: boolean;
  shortcut?: string;
  onClick?: () => void;
  children?: MenuItemConfig[];
}

interface MenuState {
  visible: boolean;
  x: number;
  y: number;
}

interface UseContextMenuReturn {
  /** 绑定到 onContextMenu 事件 */
  open: (e: React.MouseEvent) => void;
  /** 关闭菜单 */
  close: () => void;
  /** 菜单是否可见 */
  isVisible: boolean;
  /** 菜单位置 */
  position: { x: number; y: number };
  /** 渲染菜单 */
  renderMenu: () => JSX.Element | null;
}

export function useContextMenu(items: MenuItemConfig[]): UseContextMenuReturn {
  const [state, setState] = useState<MenuState>({ visible: false, x: 0, y: 0 });
  const menuRef = useRef<HTMLDivElement>(null);

  const open = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    // 边界检测
    const menuWidth = 200;
    const menuHeight = items.length * 36 + 16;
    let x = e.clientX;
    let y = e.clientY;

    if (x + menuWidth > window.innerWidth) {
      x = window.innerWidth - menuWidth - 8;
    }
    if (y + menuHeight > window.innerHeight) {
      y = window.innerHeight - menuHeight - 8;
    }

    setState({ visible: true, x, y });
  }, [items.length]);

  const close = useCallback(() => {
    setState((prev) => ({ ...prev, visible: false }));
  }, []);

  // 点击外部关闭
  useEffect(() => {
    if (!state.visible) return;

    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        close();
      }
    };

    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };

    const handleScroll = () => close();

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleEsc);
    document.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleEsc);
      document.removeEventListener("scroll", handleScroll, true);
    };
  }, [state.visible, close]);

  const renderMenu = useCallback((): JSX.Element | null => {
    if (!state.visible) return null;

    return (
      <div
        ref={menuRef}
        className="fixed z-[9999] min-w-[180px] rounded-lg border border-neutral-700 bg-neutral-900 py-1 shadow-2xl"
        style={{ left: state.x, top: state.y }}
      >
        {items.map((item, i) => {
          if (item.type === "divider") {
            return <div key={i} className="my-1 h-px bg-neutral-700" />;
          }

          return (
            <button
              key={i}
              disabled={item.disabled}
              onClick={() => {
                if (!item.disabled) {
                  item.onClick?.();
                  close();
                }
              }}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition ${
                item.disabled
                  ? "cursor-not-allowed text-neutral-600"
                  : item.danger
                    ? "text-red-400 hover:bg-red-500/10"
                    : "text-neutral-200 hover:bg-neutral-800"
              }`}
            >
              {item.icon && <span className="w-4">{item.icon}</span>}
              <span className="flex-1">{item.label}</span>
              {item.shortcut && (
                <span className="text-xs text-neutral-500">{item.shortcut}</span>
              )}
            </button>
          );
        })}
      </div>
    );
  }, [state, items, close]);

  return {
    open,
    close,
    isVisible: state.visible,
    position: { x: state.x, y: state.y },
    renderMenu,
  };
}

export default useContextMenu;
