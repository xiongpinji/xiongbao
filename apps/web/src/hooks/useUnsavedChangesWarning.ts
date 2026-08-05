import { useEffect } from "react";

/**
 * 存在未保存变更时，拦截浏览器刷新 / 关闭标签页 / 关闭浏览器，弹出原生确认框。
 *
 * 说明：
 * - 仅覆盖 `beforeunload`（刷新、关闭），不拦截应用内路由跳转
 *   （当前使用 <BrowserRouter>，react-router 的 useBlocker 需 data router 才可用）。
 * - 现代浏览器会忽略自定义文案，统一展示浏览器默认提示，但仍需设置
 *   `returnValue` 才能触发拦截。
 *
 * @param dirty 是否存在未保存变更；为 false 时不注册任何监听。
 */
export function useUnsavedChangesWarning(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
}
