import { useState } from "react";
import { clearToken, getToken, setToken } from "../../api/client";

export default function GeneralSettings() {
  const [token, setTok] = useState(getToken() ?? "");
  const [message, setMessage] = useState<string | null>(null);

  return (
    <div className="max-w-3xl space-y-6">
      <SectionTitle title="常规" description="管理当前工作台的基础访问配置。" />
      <div className="black-diamond-panel p-5">
        <div className="mb-4">
          <div className="text-sm font-medium text-white">访问 Token</div>
          <div className="mt-1 text-xs text-neutral-500">请使用后端签发的 Bearer token 管理当前工作台访问。</div>
        </div>
        <label className="block space-y-2">
          <span className="text-xs font-medium text-neutral-400">Token</span>
          <input
            className="w-full rounded-2xl border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm font-mono text-neutral-100 outline-none transition focus:border-neutral-500"
            value={token}
            onChange={(e) => setTok(e.target.value)}
            placeholder="Bearer token"
          />
        </label>
        <div className="mt-4 flex gap-2">
          <button
            className="gold-button"
            onClick={() => {
              setToken(token);
              setMessage("已保存访问 Token");
            }}
          >
            保存
          </button>
          <button
            className="rounded-full border border-white/[0.08] bg-white/[0.04] px-4 py-2 text-sm text-neutral-300 transition hover:bg-white/[0.08] hover:text-white active:scale-[0.98]"
            onClick={() => {
              clearToken();
              setTok("");
              setMessage("已清除访问 Token");
            }}
          >
            清除
          </button>
        </div>
        {message && <div className="mt-3 text-xs text-emerald-400">{message}</div>}
      </div>
    </div>
  );
}

export function SectionTitle({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight text-white">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-500">{description}</p>
    </div>
  );
}
