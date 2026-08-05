/**
 * 权限控制 Hook（零依赖）。
 *
 * 功能：
 * - usePermission：基于角色的权限检查
 * - can / cannot 快捷判断
 * - PermissionGate 条件渲染组件
 * - 支持多角色 + 通配符
 *
 * 用法：
 *   const { can, cannot, PermissionGate } = usePermission(["admin", "editor"]);
 *   if (can("user:delete")) doDelete();
 *   <PermissionGate requires="billing:manage">...</PermissionGate>
 */

import { useCallback, useMemo } from "react";

/** 权限映射：角色 → 允许的权限列表 */
const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: ["*"], // 管理员拥有所有权限
  editor: [
    "agent:create",
    "agent:edit",
    "agent:delete",
    "workflow:create",
    "workflow:edit",
    "content:publish",
    "knowledge:manage",
  ],
  viewer: ["agent:view", "workflow:view", "content:view", "knowledge:view"],
  billing: ["billing:manage", "billing:view", "subscription:manage"],
};

interface UsePermissionReturn {
  /** 检查是否有权限 */
  can: (permission: string) => boolean;
  /** 检查是否无权限 */
  cannot: (permission: string) => boolean;
  /** 检查是否有任一权限 */
  canAny: (permissions: string[]) => boolean;
  /** 检查是否有全部权限 */
  canAll: (permissions: string[]) => boolean;
  /** 条件渲染组件 */
  PermissionGate: ({
    requires,
    fallback,
    children,
  }: {
    requires: string | string[];
    fallback?: React.ReactNode;
    children: React.ReactNode;
  }) => JSX.Element | null;
}

/**
 * 权限控制 Hook。
 *
 * @param roles 当前用户角色列表
 */
export function usePermission(roles: string[]): UsePermissionReturn {
  // 汇总所有角色的权限
  const permissions = useMemo(() => {
    const set = new Set<string>();
    for (const role of roles) {
      const perms = ROLE_PERMISSIONS[role] || [];
      for (const p of perms) {
        set.add(p);
      }
    }
    return set;
  }, [roles]);

  const can = useCallback(
    (permission: string): boolean => {
      if (permissions.has("*")) return true;
      if (permissions.has(permission)) return true;

      // 通配符匹配：user:* 匹配 user:delete
      const [resource] = permission.split(":");
      if (permissions.has(`${resource}:*`)) return true;

      return false;
    },
    [permissions],
  );

  const cannot = useCallback(
    (permission: string): boolean => !can(permission),
    [can],
  );

  const canAny = useCallback(
    (perms: string[]): boolean => perms.some((p) => can(p)),
    [can],
  );

  const canAll = useCallback(
    (perms: string[]): boolean => perms.every((p) => can(p)),
    [can],
  );

  const PermissionGate = useCallback(
    ({
      requires,
      fallback = null,
      children,
    }: {
      requires: string | string[];
      fallback?: React.ReactNode;
      children: React.ReactNode;
    }): JSX.Element | null => {
      const perms = Array.isArray(requires) ? requires : [requires];
      const allowed = perms.every((p) => can(p));

      if (allowed) return <>{children}</>;
      if (fallback) return <>{fallback}</>;
      return null;
    },
    [can],
  );

  return { can, cannot, canAny, canAll, PermissionGate };
}

/** 注册自定义角色权限（应用启动时调用） */
export function registerRolePermissions(
  role: string,
  perms: string[],
): void {
  ROLE_PERMISSIONS[role] = perms;
}

export default usePermission;
