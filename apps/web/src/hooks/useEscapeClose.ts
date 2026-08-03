import { useEffect, useRef } from "react";

/**
 * 浮层打开时监听 Esc 键并触发关闭回调，保证键盘可关闭（可达性）。
 *
 * 适用：模态框、下拉菜单、右键菜单、弹出面板等。
 * - 仅在 `active` 为 true 时注册监听，关闭后自动清理。
 * - 通过 ref 持有最新 `onClose`，避免回调每次渲染重建导致监听反复注册。
 *
 * 注意：监听挂在 window 上，与项目内 useConfirm / useContextMenu 的 Esc 处理一致；
 * 同一时刻通常只有一个浮层打开，嵌套场景需自行管理层级。
 *
 * @param active 浮层是否打开
 * @param onClose 关闭回调
 */
export function useEscapeClose(active: boolean, onClose: () => void): void {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!active) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active]);
}
