import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
      navigate("/chat");
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "登录失败，请检查用户名密码";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="bg-white border rounded-lg shadow-sm p-8 w-96">
        <h1 className="text-xl font-semibold text-brand-700 mb-1">X-Agent</h1>
        <p className="text-sm text-slate-500 mb-6">面向企业的自主智能体框架</p>

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            className="w-full border rounded-md px-3 py-2 text-sm"
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
          <input
            className="w-full border rounded-md px-3 py-2 text-sm"
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button
            type="submit"
            className="w-full px-4 py-2 bg-brand-600 text-white rounded-md text-sm disabled:opacity-50"
            disabled={loading || !username.trim() || !password.trim()}
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>

        <div className="mt-4 text-xs text-slate-400 text-center">
          默认 admin/admin · lite 模式可匿名
        </div>
      </div>
    </div>
  );
}
