import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api/client";
import AppShell from "./components/layout/AppShell";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";

const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const WorkflowsPage = lazy(() => import("./pages/WorkflowsPage"));
const CreativeStudioPage = lazy(() => import("./pages/CreativeStudioPage"));
const CanvasPage = lazy(() => import("./pages/CanvasPage"));
const EditorPage = lazy(() => import("./pages/EditorPage"));
const OpenSourcePage = lazy(() => import("./pages/OpenSourcePage"));
const MemoryPage = lazy(() => import("./pages/MemoryPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const RunPage = lazy(() => import("./pages/RunPage"));

function RouteLoadingFallback() {
  return (
    <div className="flex min-h-full items-center justify-center p-8 text-sm text-neutral-400">
      正在加载页面...
    </div>
  );
}

export default function App() {
  // lite 模式后端允许匿名；full 模式需登录。
  const loggedIn = !!getToken();

  // 未登录时只显示登录页（lite 模式后端允许匿名，用户也可跳过）
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
      <Suspense fallback={<RouteLoadingFallback />}>
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/creative" element={<CreativeStudioPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />

          {/* 兼容旧入口：不再显示在主导航中。 */}
          <Route path="/canvas" element={<CanvasPage />} />
          <Route path="/editor" element={<EditorPage />} />
          <Route path="/open-source" element={<OpenSourcePage />} />
          <Route path="/memory" element={<MemoryPage />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
