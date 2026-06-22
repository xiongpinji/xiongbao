import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api/client";
import AppShell from "./components/layout/AppShell";
import ChatPage from "./pages/ChatPage";
import AgentsPage from "./pages/AgentsPage";
import WorkflowsPage from "./pages/WorkflowsPage";
import CreativeStudioPage from "./pages/CreativeStudioPage";
import CanvasPage from "./pages/CanvasPage";
import EditorPage from "./pages/EditorPage";
import OpenSourcePage from "./pages/OpenSourcePage";
import MemoryPage from "./pages/MemoryPage";
import LoginPage from "./pages/LoginPage";
import SettingsPage from "./pages/SettingsPage";

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
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/creative" element={<CreativeStudioPage />} />
        <Route path="/settings" element={<SettingsPage />} />

        {/* 兼容旧入口：不再显示在主导航中。 */}
        <Route path="/canvas" element={<CanvasPage />} />
        <Route path="/editor" element={<EditorPage />} />
        <Route path="/open-source" element={<OpenSourcePage />} />
        <Route path="/memory" element={<MemoryPage />} />
      </Routes>
    </AppShell>
  );
}
