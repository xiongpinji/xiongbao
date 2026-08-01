/**
 * 全局应用状态管理（Zustand）。
 *
 * 整合分散的 UI 状态为统一 store：
 * - 用户会话（token、角色、租户）
 * - UI 偏好（主题、语言、侧边栏）
 * - 通知队列
 * - WebSocket 连接状态
 */

import { create } from "zustand";

// ─── 类型 ───

interface UserInfo {
  userId: string;
  tenantId: string;
  roles: string[];
}

interface Notification {
  id: string;
  type: "info" | "success" | "warning" | "error";
  message: string;
  createdAt: number;
}

type WSStatus = "disconnected" | "connecting" | "connected" | "error";

interface AppState {
  // 用户
  user: UserInfo | null;
  setUser: (u: UserInfo | null) => void;

  // UI 偏好
  locale: "zh" | "en";
  setLocale: (l: "zh" | "en") => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // 通知
  notifications: Notification[];
  addNotification: (type: Notification["type"], message: string) => void;
  removeNotification: (id: string) => void;
  clearNotifications: () => void;

  // WebSocket
  wsStatus: WSStatus;
  setWsStatus: (s: WSStatus) => void;
  onlineCount: number;
  setOnlineCount: (n: number) => void;
}

// ─── Store ───

export const useAppStore = create<AppState>((set, get) => ({
  // 用户
  user: null,
  setUser: (user) => set({ user }),

  // UI 偏好
  locale: (localStorage.getItem("xagent_locale") as "zh" | "en") || "zh",
  setLocale: (locale) => {
    localStorage.setItem("xagent_locale", locale);
    set({ locale });
  },
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  // 通知
  notifications: [],
  addNotification: (type, message) => {
    const id = Math.random().toString(36).slice(2, 10);
    const notification: Notification = { id, type, message, createdAt: Date.now() };
    set((s) => ({ notifications: [...s.notifications.slice(-9), notification] }));
    // 自动移除（5s）
    setTimeout(() => get().removeNotification(id), 5000);
  },
  removeNotification: (id) =>
    set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) })),
  clearNotifications: () => set({ notifications: [] }),

  // WebSocket
  wsStatus: "disconnected",
  setWsStatus: (wsStatus) => set({ wsStatus }),
  onlineCount: 0,
  setOnlineCount: (onlineCount) => set({ onlineCount }),
}));

// ─── 选择器（避免不必要重渲染） ───

export const selectUser = (s: AppState) => s.user;
export const selectLocale = (s: AppState) => s.locale;
export const selectNotifications = (s: AppState) => s.notifications;
export const selectWsStatus = (s: AppState) => s.wsStatus;
