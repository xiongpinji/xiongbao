/**
 * 通知权限 Hook（零依赖）。
 *
 * 功能：
 * - useNotification：浏览器通知权限管理
 * - 请求权限 + 发送通知
 * - 权限状态跟踪
 *
 * 用法：
 *   const { permission, requestPermission, notify } = useNotification();
 *   <button onClick={() => notify("任务完成", { body: "Agent 执行成功" })}>通知</button>
 */

import { useCallback, useEffect, useState } from "react";

type NotificationPermissionState = "default" | "granted" | "denied" | "unsupported";

interface UseNotificationReturn {
  /** 当前权限状态 */
  permission: NotificationPermissionState;
  /** 请求权限 */
  requestPermission: () => Promise<NotificationPermissionState>;
  /** 发送通知 */
  notify: (title: string, options?: NotificationOptions) => void;
  /** 是否支持通知 */
  isSupported: boolean;
}

export function useNotification(): UseNotificationReturn {
  const isSupported =
    typeof window !== "undefined" && "Notification" in window;

  const [permission, setPermission] = useState<NotificationPermissionState>(
    () => {
      if (!isSupported) return "unsupported";
      return Notification.permission as NotificationPermissionState;
    },
  );

  // 监听权限变化（多标签同步）
  useEffect(() => {
    if (!isSupported) return;
    const handler = () => {
      setPermission(Notification.permission as NotificationPermissionState);
    };
    // 某些浏览器支持 permissionchange
    const perm = (navigator as any).permissions;
    if (perm) {
      perm.query({ name: "notifications" }).then((status: any) => {
        status.addEventListener?.("change", handler);
      });
    }
    return () => {
      // cleanup handled by GC
    };
  }, [isSupported]);

  const requestPermission =
    useCallback(async (): Promise<NotificationPermissionState> => {
      if (!isSupported) return "unsupported";

      try {
        const result = await Notification.requestPermission();
        setPermission(result as NotificationPermissionState);
        return result as NotificationPermissionState;
      } catch {
        return "denied";
      }
    }, [isSupported]);

  const notify = useCallback(
    (title: string, options?: NotificationOptions) => {
      if (!isSupported || Notification.permission !== "granted") return;

      try {
        const notification = new Notification(title, {
          icon: "/favicon.ico",
          badge: "/favicon.ico",
          ...options,
        });

        notification.onclick = () => {
          window.focus();
          notification.close();
        };

        // 自动关闭（5秒）
        setTimeout(() => notification.close(), 5000);
      } catch {
        // 静默失败
      }
    },
    [isSupported],
  );

  return { permission, requestPermission, notify, isSupported };
}

export default useNotification;
