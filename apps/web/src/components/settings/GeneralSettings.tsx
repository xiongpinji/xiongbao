import { useEffect, useState } from "react";
import { clearToken, getToken, setToken } from "../../api/client";
import { btnGhost, btnPrimary, inputCls, Row, SectionHeader } from "./ui";
import { useUnsavedChangesWarning } from "../../hooks/useUnsavedChangesWarning";

export default function GeneralSettings() {
  const [token, setTok] = useState("");
  const [hasStoredToken, setHasStoredToken] = useState(() => Boolean(getToken()));
  const [message, setMessage] = useState<string | null>(null);

  // 输入框只保存待提交值，已持久化的 Token 不回填到 DOM。
  useUnsavedChangesWarning(token.trim().length > 0);

  // 成功消息 3s 自动消失
  useEffect(() => {
    if (!message) return;
    const t = window.setTimeout(() => setMessage(null), 3000);
    return () => window.clearTimeout(t);
  }, [message]);

  return (
    <div className="max-w-2xl">
      <SectionHeader title="general" desc="管理当前工作台的基础访问配置。" />
      <Row
        label="访问 Token"
        hint={hasStoredToken ? "已保存（输入新 Token 可替换）" : "使用后端签发的 Bearer token 管理访问。"}
        stacked
      >
        <div className="flex max-w-md items-center gap-2">
          <input
            type="password"
            className={inputCls}
            value={token}
            onChange={(e) => setTok(e.target.value)}
            placeholder="Bearer token"
          />
          <button
            className={btnPrimary}
            disabled={!token.trim()}
            onClick={() => {
              setToken(token.trim());
              setTok("");
              setHasStoredToken(true);
              setMessage("已保存访问 Token");
            }}
          >
            保存
          </button>
          <button
            className={btnGhost}
            onClick={() => {
              clearToken();
              setTok("");
              setHasStoredToken(false);
              setMessage("已清除访问 Token");
            }}
          >
            清除
          </button>
        </div>
        {message && <div className="mt-2 text-[12px] text-emerald-400">{message}</div>}
      </Row>
    </div>
  );
}

export function SectionTitle({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-b border-white/[0.07] pb-3">
      <h2 className="font-mono text-[13px] font-semibold uppercase tracking-wider text-neutral-200">
        {title}
      </h2>
      <p className="mt-1 text-[12px] leading-4 text-neutral-500">{description}</p>
    </div>
  );
}
