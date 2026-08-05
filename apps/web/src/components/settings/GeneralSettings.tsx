import { useEffect, useState } from "react";
import { clearToken, getToken, setToken } from "../../api/client";
import { useUnsavedChangesWarning } from "../../hooks/useUnsavedChangesWarning";

export default function GeneralSettings() {
  const [token, setTok] = useState(getToken() ?? "");
  const [message, setMessage] = useState<string | null>(null);

  // 输入的 Token 与已保存值不一致时，拦截刷新/关闭，避免未保存的 Token 丢失
  useUnsavedChangesWarning(token.trim() !== (getToken() ?? ""));

  // 成功消息 3s 自动消失
  useEffect(() => {
    if (!message) return;
    const t = window.setTimeout(() => setMessage(null), 3000);
    return () => window.clearTimeout(t);
  }, [message]);

  return (
    <div className="max-w-2xl space-y-6">
      <SectionTitle title="常规" description="管理当前工作台的基础访问配置。" />
      <div className="space-y-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
        <div>
          <div className="text-sm font-medium text-neutral-200">访问 Token</div>
          <div className="mt-1 text-[12px] text-neutral-500">使用后端签发的 Bearer token 管理访问。</div>
        </div>
        <label className="block space-y-1.5">
          <span className="text-[12px] text-neutral-400">Token</span>
          <input
            className="w-full rounded-md border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm font-mono text-neutral-100 outline-none transition focus:border-white/[0.16]"
            value={token}
            onChange={(e) => setTok(e.target.value)}
            placeholder="Bearer token"
          />
        </label>
        <div className="flex gap-2">
          <button
            className="rounded-md bg-white px-4 py-2 text-sm font-medium text-black transition hover:bg-neutral-200 disabled:opacity-40"
            disabled={!token.trim()}
            onClick={() => {
              setToken(token.trim());
              setMessage("已保存访问 Token");
            }}
          >
            保存
          </button>
          <button
            className="rounded-md border border-white/[0.08] px-4 py-2 text-sm text-neutral-400 transition hover:bg-white/[0.04]"
            onClick={() => {
              clearToken();
              setTok("");
              setMessage("已清除访问 Token");
            }}
          >
            清除
          </button>
        </div>
        {message && <div className="text-[12px] text-emerald-400">{message}</div>}
      </div>
    </div>
  );
}

export function SectionTitle({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h2 className="text-base font-medium text-neutral-100">{title}</h2>
      <p className="mt-1 text-[13px] text-neutral-500">{description}</p>
    </div>
  );
}
