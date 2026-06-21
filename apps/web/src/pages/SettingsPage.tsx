import { useState } from "react";
import { setToken, clearToken, getToken } from "../api/client";

export default function SettingsPage() {
  const [token, setTok] = useState(getToken() ?? "");

  return (
    <div className="p-6 max-w-xl space-y-4">
      <h1 className="text-xl font-semibold">设置</h1>
      <div className="bg-white border rounded-md p-4 space-y-2">
        <div className="text-sm font-medium">访问 Token（lite 模式可留空）</div>
        <input
          className="w-full border rounded px-2 py-1 text-sm font-mono"
          value={token}
          onChange={(e) => setTok(e.target.value)}
          placeholder="Bearer token"
        />
        <div className="flex gap-2">
          <button
            className="px-3 py-1 bg-brand-600 text-white rounded text-sm"
            onClick={() => {
              setToken(token);
              alert("已保存");
            }}
          >
            保存
          </button>
          <button
            className="px-3 py-1 border rounded text-sm"
            onClick={() => {
              clearToken();
              setTok("");
            }}
          >
            清除
          </button>
        </div>
      </div>
    </div>
  );
}
