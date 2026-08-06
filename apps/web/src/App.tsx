import { lazy, Suspense, useEffect } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { isLoggedIn } from "./api/client";
import AppShell from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";

const ChatPage = lazy(() => import("./pages/ChatPage"));
const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const ProfessionalModePage = lazy(() => import("./pages/ProfessionalModePage"));
const ExcludedModulePage = lazy(() => import("./pages/ExcludedModulePage"));
const OpenSourcePage = lazy(() => import("./pages/OpenSourcePage"));
const MemoryPage = lazy(() => import("./pages/MemoryPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const GoalBoardPage = lazy(() => import("./pages/GoalBoardPage"));
const RunPage = lazy(() => import("./pages/RunPage"));
const BillingPage = lazy(() => import("./pages/BillingPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));
const SupervisorPage = lazy(() => import("./pages/SupervisorPage"));
const DevelopmentTasksPage = lazy(() => import("./pages/DevelopmentTasksPage"));

function PageFallback() {
  return (
    <div className="flex min-h-[320px] items-center justify-center text-sm text-neutral-500">
      加载中...
    </div>
  );
}

function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <div className="text-6xl font-bold tracking-tight text-neutral-700">404</div>
      <p className="text-sm text-neutral-500">页面不存在或已被移动</p>
      <Link
        to="/chat"
        className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition hover:bg-neutral-200"
      >
        返回对话
      </Link>
    </div>
  );
}

function ProfessionalRedirect() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set("mode", "workflow");
  return <Navigate to={`/professional?${params.toString()}${location.hash}`} replace />;
}

export default function App() {
  const location = useLocation();
  const loggedIn = isLoggedIn();

  useEffect(() => {
    if (!loggedIn) {
      document.title = "登录 · X-Agent";
    }
  }, [loggedIn]);

  if (!loggedIn) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <AppShell>
      {/* 路由级错误边界：单个页面崩溃时仅主内容区降级，侧栏/导航/命令面板保持可用；
          key 随路由变化重置边界，避免报错后导航到其他页面仍停留在错误屏 */}
      <ErrorBoundary key={location.pathname}>
        <Suspense fallback={<PageFallback />}>
          <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/home" element={<ChatPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/supervisor" element={<SupervisorPage />} />
          <Route path="/goal-board" element={<GoalBoardPage />} />
          <Route path="/development-tasks" element={<DevelopmentTasksPage />} />
          <Route path="/professional" element={<ProfessionalModePage />} />
          <Route path="/workflows" element={<ProfessionalRedirect />} />
          <Route path="/creative" element={<ExcludedModulePage />} />
          <Route path="/creative/canvas" element={<ExcludedModulePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/billing" element={<BillingPage />} />
          <Route path="/audit" element={<AuditPage />} />

          {/* 兼容旧入口：不再显示在主导航中。 */}
          <Route path="/canvas" element={<ExcludedModulePage />} />
          <Route path="/editor" element={<ExcludedModulePage />} />
          <Route path="/open-source" element={<OpenSourcePage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
        </Suspense>
      </ErrorBoundary>
    </AppShell>
  );
}
