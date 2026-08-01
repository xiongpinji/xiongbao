/**
 * 路由守卫：权限控制 + 角色拦截。
 *
 * 用法：
 *   <RouteGuard roles={["admin"]} fallback={<NoAccess />}>
 *     <AdminPage />
 *   </RouteGuard>
 *
 * 配合 appStore 中的 user.roles 判断。
 */

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAppStore } from "../store/appStore";

interface RouteGuardProps {
  children: ReactNode;
  /** 允许访问的角色列表（空 = 仅需登录） */
  roles?: string[];
  /** 无权限时的降级 UI（默认跳转 /chat） */
  fallback?: ReactNode;
}

export function RouteGuard({ children, roles, fallback }: RouteGuardProps) {
  const user = useAppStore((s) => s.user);
  const location = useLocation();

  // 未登录 → 跳转登录
  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  // 角色检查
  if (roles && roles.length > 0) {
    const hasRole = user.roles.some((r) => roles.includes(r));
    if (!hasRole) {
      if (fallback) return <>{fallback}</>;
      return (
        <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 text-center">
          <div className="text-3xl">🔒</div>
          <p className="text-sm text-neutral-400">
            需要 {roles.join(" / ")} 角色权限
          </p>
          <Navigate to="/chat" replace />
        </div>
      );
    }
  }

  return <>{children}</>;
}

/** 管理员专用守卫 */
export function AdminGuard({ children }: { children: ReactNode }) {
  return <RouteGuard roles={["admin"]}>{children}</RouteGuard>;
}

export default RouteGuard;
