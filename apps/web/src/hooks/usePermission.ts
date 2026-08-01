/**
 * 权限管理 Hook（零依赖）。
 *
 * 功能：
 * - usePermission：查询浏览器权限状态
 * - 实时监听权限变化
 * - 支持 geolocation/notifications/camera 等
 *
 * 用法：
 *   const status = usePermission("geolocation");
 *   // "granted" | "denied" | "prompt" | "unknown"
 */

import { useEffect, useState } from "react";

type PermissionStatus = "granted" | "denied" | "prompt" | "unknown";

export function usePermission(name: string): PermissionStatus {
  const [status, setStatus] = useState<PermissionStatus>("unknown");

  useEffect(() => {
    if (!navigator.permissions) {
      setStatus("unknown");
      return;
    }

    let permissionStatus: PermissionStatus | null = null;

    const handleChange = () => {
      if (permissionStatus) {
        setStatus(permissionStatus.state as PermissionStatus);
      }
    };

    navigator.permissions
      .query({ name: name as PermissionName })
      .then((result) => {
        permissionStatus = result;
        setStatus(result.state as PermissionStatus);
        result.addEventListener("change", handleChange);
      })
      .catch(() => {
        setStatus("unknown");
      });

    return () => {
      if (permissionStatus) {
        permissionStatus.removeEventListener("change", handleChange);
      }
    };
  }, [name]);

  return status;
}

/** 批量查询多个权限。 */
export function usePermissions(names: string[]): Record<string, PermissionStatus> {
  const [statuses, setStatuses] = useState<Record<string, PermissionStatus>>(() =>
    Object.fromEntries(names.map((n) => [n, "unknown" as PermissionStatus])),
  );

  useEffect(() => {
    if (!navigator.permissions) return;

    const controllers: { status: PermissionStatus; handler: () => void }[] = [];

    names.forEach((name) => {
      navigator.permissions
        .query({ name: name as PermissionName })
        .then((result) => {
          setStatuses((prev) => ({ ...prev, [name]: result.state as PermissionStatus }));
          const handler = () => {
            setStatuses((prev) => ({ ...prev, [name]: result.state as PermissionStatus }));
          };
          result.addEventListener("change", handler);
          controllers.push({ status: result, handler });
        })
        .catch(() => {
          setStatuses((prev) => ({ ...prev, [name]: "unknown" }));
        });
    });

    return () => {
      controllers.forEach(({ status, handler }) => {
        status.removeEventListener("change", handler);
      });
    };
  }, [names.join(",")]);

  return statuses;
}

export default usePermission;
