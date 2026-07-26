import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { isLoggedIn } from "./api/client";
import AppShell from "./components/layout/AppShell";
import LoginPage from "./pages/LoginPage";

const ChatPage = lazy(() => import("./pages/ChatPage"));
const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const ProfessionalModePage = lazy(() => import("./pages/ProfessionalModePage"));
const CreativeStudioPage = lazy(() => import("./pages/CreativeStudioPage"));
const EditorPage = lazy(() => import("./pages/EditorPage"));
const OpenSourcePage = lazy(() => import("./pages/OpenSourcePage"));
const MemoryPage = lazy(() => import("./pages/MemoryPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const GoalBoardPage = lazy(() => import("./pages/GoalBoardPage"));
const RunPage = lazy(() => import("./pages/RunPage"));
const BillingPage = lazy(() => import("./pages/BillingPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));

function PageFallback() {
  return (
    <div className="flex min-h-[320px] items-center justify-center text-sm text-neutral-500">
      加载中...
    </div>
  );
}

function ProfessionalRedirect({ mode }: { mode: "drama" | "workflow" }) {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set("mode", mode);
  return <Navigate to={`/professional?${params.toString()}${location.hash}`} replace />;
}

export default function App() {
  const location = useLocation();
  const loggedIn = isLoggedIn();

  if (!loggedIn) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  if (location.pathname === "/creative/canvas") {
    return (
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/creative/canvas" element={<CreativeStudioPage variant="canvas" />} />
          <Route path="*" element={<Navigate to="/creative/canvas" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <AppShell>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/home" element={<ChatPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/goal-board" element={<GoalBoardPage />} />
          <Route path="/professional" element={<ProfessionalModePage />} />
          <Route path="/workflows" element={<ProfessionalRedirect mode="workflow" />} />
          <Route path="/creative" element={<Navigate to="/creative/canvas" replace />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/billing" element={<BillingPage />} />
          <Route path="/audit" element={<AuditPage />} />

          {/* 兼容旧入口：不再显示在主导航中。 */}
          <Route path="/canvas" element={<Navigate to="/creative/canvas" replace />} />
          <Route path="/editor" element={<EditorPage />} />
          <Route path="/open-source" element={<OpenSourcePage />} />
          <Route path="/memory" element={<MemoryPage />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
