import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import {
  Bot, Workflow, Film, Search, Brain, Settings,
  MessageSquare, Scissors, Layout,
} from "lucide-react";
import { getToken } from "./api/client";
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

const nav = [
  { to: "/chat", label: "对话", icon: MessageSquare },
  { to: "/agents", label: "智能体", icon: Bot },
  { to: "/workflows", label: "工作流", icon: Workflow },
  { to: "/canvas", label: "制作画布", icon: Layout },
  { to: "/creative", label: "短剧工厂", icon: Film },
  { to: "/editor", label: "视频剪辑", icon: Scissors },
  { to: "/open-source", label: "开源发现", icon: Search },
  { to: "/memory", label: "知识库", icon: Brain },
  { to: "/settings", label: "设置", icon: Settings },
];

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
    <div className="flex h-screen">
      <aside className="w-56 shrink-0 border-r border-slate-200 bg-white flex flex-col">
        <div className="px-4 py-4 font-bold text-brand-700 text-lg">X-Agent</div>
        <nav className="flex-1 px-2 space-y-1">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-md text-sm ${
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              <n.icon size={16} />
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/canvas" element={<CanvasPage />} />
          <Route path="/creative" element={<CreativeStudioPage />} />
          <Route path="/editor" element={<EditorPage />} />
          <Route path="/open-source" element={<OpenSourcePage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
