import { useCallback, useEffect, useState } from "react";
import { KeyRound, Plus, Shield, Trash2, UserPlus, Users, XCircle } from "lucide-react";
import { api } from "../../api/client";

interface TenantUser {
  user_id: string;
  tenant_id: string;
  roles: string[];
  email: string;
}

interface ApiKeyView {
  key_id: string;
  name: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  revoked: boolean;
}

interface TenantInfo {
  tenant_id: string;
  user_count: number;
  api_key_count: number;
  roles_available: string[];
}

export default function TeamSettings() {
  const [info, setInfo] = useState<TenantInfo | null>(null);
  const [users, setUsers] = useState<TenantUser[]>([]);
  const [keys, setKeys] = useState<ApiKeyView[]>([]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState("");
  // 创建用户表单
  const [showUserForm, setShowUserForm] = useState(false);
  const [uName, setUName] = useState("");
  const [uPass, setUPass] = useState("");
  const [uRole, setURole] = useState("member");
  // 创建 Key 表单
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [kName, setKName] = useState("");
  const [kScopes, setKScopes] = useState("*");

  const refresh = useCallback(async () => {
    try {
      const [infoR, usersR, keysR] = await Promise.all([
        api.get("/tenants/info"),
        api.get("/tenants/users"),
        api.get("/tenants/api-keys"),
      ]);
      setInfo(infoR.data);
      setUsers(usersR.data.users);
      setKeys(keysR.data.keys);
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const createUser = async () => {
    try {
      await api.post("/tenants/users", { username: uName, password: uPass, roles: [uRole] });
      setShowUserForm(false);
      setUName(""); setUPass(""); setURole("member");
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建失败");
    }
  };

  const deleteUser = async (userId: string) => {
    try {
      await api.delete(`/tenants/users/${userId}`);
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const changeRole = async (userId: string, roles: string[]) => {
    try {
      await api.put(`/tenants/users/${userId}/roles`, { roles });
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "修改失败");
    }
  };

  const createKey = async () => {
    try {
      const resp = await api.post("/tenants/api-keys", {
        name: kName,
        scopes: kScopes.split(",").map((s) => s.trim()),
      });
      setNewKey(resp.data.raw_key);
      setShowKeyForm(false);
      setKName(""); setKScopes("*");
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建失败");
    }
  };

  const revokeKey = async (keyId: string) => {
    try {
      await api.post(`/tenants/api-keys/${keyId}/revoke`);
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "吊销失败");
    }
  };

  const deleteKey = async (keyId: string) => {
    try {
      await api.delete(`/tenants/api-keys/${keyId}`);
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* 新 Key 一次性提示 */}
      {newKey && (
        <div className="rounded-xl border border-[#d6ad62]/40 bg-[#d6ad62]/10 px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[#d6ad62]">API Key 已创建（仅显示一次）</span>
            <button onClick={() => setNewKey(null)} className="text-neutral-400 hover:text-white"><XCircle size={16} /></button>
          </div>
          <code className="mt-2 block break-all rounded-lg bg-black/40 px-3 py-2 text-xs text-green-300">{newKey}</code>
        </div>
      )}

      {/* 租户概览 */}
      {info && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "租户 ID", value: info.tenant_id, icon: Shield },
            { label: "用户数", value: String(info.user_count), icon: Users },
            { label: "API Key", value: String(info.api_key_count), icon: KeyRound },
          ].map((c) => (
            <div key={c.label} className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-4">
              <c.icon size={18} className="mb-2 text-[#d6ad62]" />
              <div className="text-lg font-semibold text-white">{c.value}</div>
              <div className="text-xs text-neutral-500">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* 用户管理 */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">用户管理</h3>
          <button
            onClick={() => setShowUserForm(!showUserForm)}
            className="flex items-center gap-1.5 rounded-xl bg-[#d6ad62]/15 px-3 py-1.5 text-sm text-[#d6ad62] transition hover:bg-[#d6ad62]/25"
          >
            <UserPlus size={15} /> 添加用户
          </button>
        </div>

        {showUserForm && (
          <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-white/[0.07] bg-white/[0.03] p-4">
            <div>
              <label className="mb-1 block text-xs text-neutral-400">用户名</label>
              <input value={uName} onChange={(e) => setUName(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white outline-none focus:border-[#d6ad62]/50" placeholder="username" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-neutral-400">密码</label>
              <input type="password" value={uPass} onChange={(e) => setUPass(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white outline-none focus:border-[#d6ad62]/50" placeholder="••••••" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-neutral-400">角色</label>
              <select value={uRole} onChange={(e) => setURole(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white outline-none">
                <option value="admin">admin</option>
                <option value="member">member</option>
                <option value="viewer">viewer</option>
              </select>
            </div>
            <button onClick={createUser} className="rounded-lg bg-[#d6ad62] px-4 py-1.5 text-sm font-medium text-black transition hover:brightness-110">创建</button>
          </div>
        )}

        <div className="space-y-2">
          {users.map((u) => (
            <div key={u.user_id} className="flex items-center justify-between rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
              <div>
                <span className="text-sm font-medium text-white">{u.user_id}</span>
                {u.email && <span className="ml-2 text-xs text-neutral-500">{u.email}</span>}
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={u.roles[0] || "member"}
                  onChange={(e) => changeRole(u.user_id, [e.target.value])}
                  className="rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-xs text-white outline-none"
                >
                  <option value="admin">admin</option>
                  <option value="member">member</option>
                  <option value="viewer">viewer</option>
                </select>
                <button onClick={() => deleteUser(u.user_id)} className="text-neutral-500 transition hover:text-red-400">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* API Key 管理 */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">API Key</h3>
          <button
            onClick={() => setShowKeyForm(!showKeyForm)}
            className="flex items-center gap-1.5 rounded-xl bg-[#d6ad62]/15 px-3 py-1.5 text-sm text-[#d6ad62] transition hover:bg-[#d6ad62]/25"
          >
            <Plus size={15} /> 创建 Key
          </button>
        </div>

        {showKeyForm && (
          <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-white/[0.07] bg-white/[0.03] p-4">
            <div>
              <label className="mb-1 block text-xs text-neutral-400">名称</label>
              <input value={kName} onChange={(e) => setKName(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white outline-none focus:border-[#d6ad62]/50" placeholder="my-integration" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-neutral-400">Scopes（逗号分隔）</label>
              <input value={kScopes} onChange={(e) => setKScopes(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white outline-none focus:border-[#d6ad62]/50" placeholder="*" />
            </div>
            <button onClick={createKey} className="rounded-lg bg-[#d6ad62] px-4 py-1.5 text-sm font-medium text-black transition hover:brightness-110">创建</button>
          </div>
        )}

        <div className="space-y-2">
          {keys.map((k) => (
            <div key={k.key_id} className={`flex items-center justify-between rounded-xl border px-4 py-3 ${k.revoked ? "border-red-500/20 bg-red-500/5 opacity-60" : "border-white/[0.07] bg-white/[0.02]"}`}>
              <div>
                <span className="text-sm font-medium text-white">{k.name}</span>
                <span className="ml-2 text-xs text-neutral-500">{k.scopes.join(", ")}</span>
                {k.revoked && <span className="ml-2 rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] text-red-300">已吊销</span>}
              </div>
              <div className="flex items-center gap-2">
                {!k.revoked && (
                  <button onClick={() => revokeKey(k.key_id)} className="text-xs text-neutral-400 transition hover:text-amber-400">吊销</button>
                )}
                <button onClick={() => deleteKey(k.key_id)} className="text-neutral-500 transition hover:text-red-400">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
          {keys.length === 0 && <p className="text-sm text-neutral-500">暂无 API Key</p>}
        </div>
      </section>
    </div>
  );
}
