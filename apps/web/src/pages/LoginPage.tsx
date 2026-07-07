import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";
import AmbientAurora from "../components/effects/AmbientAurora";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
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
      setError(
        msg.includes("500")
          ? "后端登录服务当前不可用，请稍后重试或联系管理员。"
          : msg,
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="xagent-app-bg relative flex min-h-screen items-center justify-center overflow-hidden p-6 text-neutral-100">
      <AmbientAurora />
      <div className="xagent-surface xagent-metal-border relative z-10 w-full max-w-md p-8">
        <div className="mb-7 flex items-center gap-3">
          <div className="xagent-brand-logo h-12 w-12">
            <img src="/assets/xiongbao-logo.png" alt="熊宝智能体系统" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-white">熊宝智能体系统</h1>
            <p className="mt-1 text-sm text-neutral-500">Xiongbao Agent System</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            className="field"
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
          <input
            className="field"
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && (
            <div className="rounded-2xl border border-red-400/20 bg-red-400/5 px-3 py-2 text-sm leading-6 text-red-200">
              {error}
            </div>
          )}
          <button
            type="submit"
            className="gold-button w-full"
            disabled={loading || !username.trim() || !password.trim()}
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>

        <div className="mt-5 text-center text-xs text-neutral-600">
          请使用当前环境已初始化的账号登录。
        </div>
      </div>
    </div>
  );
}
