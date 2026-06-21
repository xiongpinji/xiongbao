import { useEffect } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import {
  Bot,
  Workflow,
  Film,
  Search,
  Brain,
  Settings,
  MessageSquare,
  Scissors,
} from "lucide-react";
import { getToken } from "./api/client";
import ChatPage from "./pages/ChatPage";
import AgentsPage from "./pages/AgentsPage";
import WorkflowsPage from "./pages/WorkflowsPage";
import CreativeStudioPage from "./pages/CreativeStudioPage";
import EditorPage from "./pages/EditorPage";
import OpenSourcePage from "./pages/OpenSourcePage";
import MemoryPage from "./pages/MemoryPage";
import SettingsPage from "./pages/SettingsPage";

const nav = [
  { to: "/chat", label: "对话", icon: MessageSquare },
  { to: "/agents", label: "智能体", icon: Bot },
  { to: "/workflows", label: "工作流", icon: Workflow },
  { to: "/creative", label: "短剧工厂", icon: Film },
  { to: "/editor", label: "视频剪辑", icon: Scissors },
  { to: "/open-source", label: "开源发现", icon: Search },
  { to: "/memory", label: "知识库", icon: Brain },
  { to: "/settings", label: "设置", icon: Settings },
];

export default function App() {
  // lite 模式后端允许匿名；full 模式需登录。此处仅做 token 存在性提示。
  useEffect(() => {
    if (!getToken()) console.info("[xagent] 未检测到 token，lite 模式可匿名使用");
  }, []);

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
