import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { getOidcProviders, login } from "../api/client";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ssoEnabled, setSsoEnabled] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    getOidcProviders()
      .then((p) => setSsoEnabled(!!p.enabled))
      .catch(() => {});
  }, []);

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
    <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a] p-6 text-neutral-100">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="xagent-brand-logo h-14 w-14">
            <img src="/assets/xiongbao-logo.png" alt="熊宝智能体系统" />
          </div>
          <h1 className="mt-4 text-lg font-semibold text-neutral-100">熊宝智能体系统</h1>
          <p className="mt-1 text-[12px] text-neutral-600">Xiongbao Agent System</p>
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
            <div className="rounded-lg border border-red-400/15 bg-red-400/5 px-3 py-2 text-[12px] leading-5 text-red-300">
              {error}
            </div>
          )}
          <button
            type="submit"
            className="w-full rounded-lg bg-white px-3 py-2.5 text-sm font-medium text-black transition hover:bg-neutral-200 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
            disabled={loading || !username.trim() || !password.trim()}
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>

        {ssoEnabled && (
          <a
            href="/api/v1/auth/oidc/login"
            className="mt-3 block w-full rounded-lg border border-neutral-700 px-3 py-2.5 text-center text-sm font-medium text-neutral-200 transition hover:bg-neutral-800 active:scale-[0.99]"
          >
            使用 SSO 登录
          </a>
        )}

        <div className="mt-6 text-center text-[11px] text-neutral-700">
          请使用当前环境已初始化的账号登录
        </div>
      </div>
    </div>
  );
}
