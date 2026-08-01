/**
 * 路由预取工具：在用户 hover 导航链接时提前加载页面 chunk。
 *
 * 用法：
 *   import { prefetchRoute } from "../api/prefetch";
 *   <Link to="/agents" onMouseEnter={() => prefetchRoute("agents")}>
 */

type RouteName =
  | "chat"
  | "agents"
  | "supervisor"
  | "professional"
  | "creative"
  | "settings"
  | "billing"
  | "audit"
  | "goal-board";

const loaders: Record<RouteName, () => Promise<unknown>> = {
  chat: () => import("../pages/ChatPage"),
  agents: () => import("../pages/AgentsPage"),
  supervisor: () => import("../pages/SupervisorPage"),
  professional: () => import("../pages/ProfessionalModePage"),
  creative: () => import("../pages/CreativeStudioPage"),
  settings: () => import("../pages/SettingsPage"),
  billing: () => import("../pages/BillingPage"),
  audit: () => import("../pages/AuditPage"),
  "goal-board": () => import("../pages/GoalBoardPage"),
};

const prefetched = new Set<string>();

/**
 * 预取指定路由的 chunk（幂等，重复调用安全）。
 */
export function prefetchRoute(name: RouteName): void {
  if (prefetched.has(name)) return;
  prefetched.add(name);
  const loader = loaders[name];
  if (loader) {
    loader().catch(() => {
      // 预取失败不影响正常导航
      prefetched.delete(name);
    });
  }
}

/**
 * 预取所有路由（适合空闲时调用）。
 */
export function prefetchAll(): void {
  (Object.keys(loaders) as RouteName[]).forEach(prefetchRoute);
}
